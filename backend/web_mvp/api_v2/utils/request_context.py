"""Request context API v2: изоляция территории и атомарное сохранение плана."""
from contextvars import ContextVar
from functools import wraps
from django.db import transaction
from rest_framework.decorators import api_view as drf_api_view
from rest_framework.response import Response
from backend.optimization import RoutingProviderError
from ..models import Territory, ReassignmentProposal, RescheduleEvent
from ..services import restore, save, import_dataset
from ..services.state import encode, decode

_current = ContextVar('request_optimization_service')


class ServiceProxy:
    """Передаёт вызовы текущему запросу, не разделяя район между пользователями."""
    def __getattr__(self, name):
        return getattr(_current.get(), name)


optimization_service = ServiceProxy()


def api_view(methods):
    """Оборачивает актуальные обработчики транзакцией и сохранением района."""
    def decorate(function):
        @wraps(function)
        def dispatch(request, *args, **kwargs):
            code = request.query_params.get('territory')
            if not code:
                return Response({'error': 'Укажите territory в строке запроса.'}, status=400)
            try:
                with transaction.atomic():
                    territory = Territory.objects.select_for_update().get(code=code)
                    service = restore(territory)
                    if function.__name__ == 'manual_reassignment_confirm_view':
                        proposal = ReassignmentProposal.objects.filter(
                            token=request.data.get('proposal_id'), territory=territory,
                            revision=territory.revision,
                        ).first()
                        if proposal:
                            service._manual_reassignment_proposals[proposal.token] = decode(proposal.payload)
                    token = _current.set(service)
                    try:
                        response = function(request, *args, **kwargs)
                    finally:
                        _current.reset(token)
                    if response.status_code >= 400:
                        transaction.set_rollback(True)
                        return response
                    if function.__name__ == 'manual_reassignment_preview_view':
                        for key, proposal in service._manual_reassignment_proposals.items():
                            ReassignmentProposal.objects.update_or_create(
                                token=key, defaults={'territory': territory, 'revision': territory.revision, 'payload': encode(proposal)},
                            )
                    elif function.__name__ not in {'explain_task_view', 'geocode_address_view'}:
                        saved = save(territory, service)
                        response.data.update(saved)
                        if function.__name__ == 'replan_view':
                            RescheduleEvent.objects.create(
                                territory=territory,
                                event_type=request.data['event_type'],
                                time=request.data['planning_time'],
                                payload=dict(request.data),
                            )
                    return response
            except Territory.DoesNotExist:
                return Response({'error': 'Район не загружен.'}, status=404)
            except (ValueError, RoutingProviderError) as exc:
                return Response({'error': str(exc)}, status=422)
        return drf_api_view(methods)(dispatch)
    return decorate
