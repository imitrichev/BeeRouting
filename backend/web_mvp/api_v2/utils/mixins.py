from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from django.db import transaction

class ACTIONS:
    LIST = 'list'
    PUT = 'update'
    PATCH = 'partial_update'
    POST = 'create'
    RETRIEVE = 'retrieve'
    DELETE = 'destroy'


class GetActionViewSet(GenericViewSet):
    actions_expand = {
        ACTIONS.LIST: ACTIONS.RETRIEVE,
        ACTIONS.PUT: ACTIONS.POST,
        ACTIONS.PATCH: ACTIONS.POST
    }

    def get_expanded_action(self, for_dict, action_expand=None):
        if action_expand is None:
            action_expand = self.actions_expand
        action = self.action
        if action not in for_dict and action in action_expand:
            action = action_expand[action]
            if isinstance(action, dict):
                return self.get_expanded_action(action)
        return action


class MultiSerializerViewSet(GetActionViewSet):
    serializers_class = {}

    def get_serializer_expanded_action(self):
        return self.get_expanded_action(self.serializers_class)

    def get_serializer_class(self):
        action = self.get_serializer_expanded_action()
        if action in self.serializers_class:
            self.serializer_class = self.serializers_class.get(action)
        return super().get_serializer_class()


class PersistentTerritoryMutationMixin:
    """Синхронизирует CRUD коллеги с domain-снимком выбранного района.

    Наследник должен изменять модель, у которой есть поле ``territory``.
    Любое изменение входных данных инвалидирует прежний маршрут; сервис
    пересобирает сценарий, а новый план появляется после следующего запуска
    оптимизации.
    """

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save()
        self._rebuild(instance.territory)

    @transaction.atomic
    def perform_update(self, serializer):
        instance = serializer.save()
        self._rebuild(instance.territory)

    @transaction.atomic
    def perform_destroy(self, instance):
        territory = instance.territory
        instance.delete()
        self._rebuild(territory)

    @staticmethod
    def _rebuild(territory):
        # Локальный импорт не создаёт цикл services -> serializers -> views.
        from ..services import rebuild_after_crud
        rebuild_after_crud(territory)
