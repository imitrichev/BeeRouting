"""Постоянное состояние районов поверх актуального сервиса планирования."""
import json
from pathlib import Path
from django.db import transaction
from backend.optimization import load_json_scenario_data, create_osrm_provider_from_environment
from backend.web_mvp.api.services import OptimizationWebService
from ..models import Territory, ReassignmentProposal
from ..state import encode, decode
from ..repository import sync_entities

STATE_FIELDS = ('_scenario', '_problem', '_result', '_preserve_assigned_tasks',
                '_ignore_task_statuses', '_unavailable_engineer_ids', '_source_name')


def restore(territory):
    """Создаёт изолированный сервис для одного запроса и одного района."""
    service = OptimizationWebService()
    for name, value in territory.state.items():
        if name in STATE_FIELDS:
            setattr(service, name, decode(value))
    if service._problem is not None:
        service.routing_provider = create_osrm_provider_from_environment(
            coordinates=service._scenario.location_coordinates,
            request_timeout_seconds=15.0,
        )
    return service


def save(territory, service):
    """Атомарно сохраняет модели ядра, матрицы, результат и геометрию."""
    response = service.serialize_response(service._scenario, service._result)
    response['planning_options'] = {
        'ignore_task_statuses': service._ignore_task_statuses,
        'preserve_assigned_tasks': service._preserve_assigned_tasks,
    }
    territory.state = {name: encode(getattr(service, name)) for name in STATE_FIELDS}
    territory.response = response
    territory.revision += 1
    territory.save()
    sync_entities(territory, service)
    ReassignmentProposal.objects.filter(territory=territory).delete()
    return response


@transaction.atomic
def import_dataset(content, filename):
    """Регистрирует район при первой загрузке; повторная загрузка сохраняет его план."""
    payload = json.loads(content.decode('utf-8'))
    scenario = load_json_scenario_data(payload)
    code = payload.get('territory_code') or scenario.scenario_name
    territory = Territory.objects.filter(code=code).first()
    if territory is not None:
        return territory
    service = OptimizationWebService()
    service._scenario = scenario
    service._source_name = filename
    office = payload.get('office_start_point') or {}
    territory = Territory.objects.create(
        code=code, name=payload.get('territory_name') or code,
        office_lat=office.get('lat'), office_lon=office.get('lon'),
        office_address=office.get('address', ''), source_name=filename,
        source_payload=payload,
    )
    save(territory, service)
    return territory
