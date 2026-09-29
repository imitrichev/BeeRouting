<script setup lang="ts">
/**
 * Таблица маршрутов инженеров с раскрывающимися строками остановок.
 *
 * Верхний уровень — список маршрутов (по одному на инженера): инженер,
 * транспорт, число остановок, дистанция и время в пути. Первая колонка —
 * чекбокс выбора маршрута для отображения на карте; выбор синхронизируется
 * с `districtDataStore.selectedRoutes`.
 *
 * При раскрытии строки показывается вложенная таблица остановок с адресом,
 * временем прибытия/работы, статусом и действиями (объяснение, переназначение,
 * изменение статуса).
 */

import BasicCard from '@/templates/BasicCard.vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, ref } from 'vue'
import type { Engineer, EngineerRoute, RouteStop } from '@/types/entities.ts'
import { getVehicleTypeTranslation } from '@/utils/translations.ts'
import { getEngineerColor } from '@/utils/map.ts'
import { getTaskStatusColor, getTaskStatusLabel, isTerminalStatus } from '@/utils/task.ts'
import IconButton from '@/templates/IconButton.vue'
import TaskExplanationDialog from '@/components/modals/TaskExplanationDialog.vue'
import ReasignmentDialog from '@/components/modals/ReasignmentDialog.vue'
import TaskStatusDialog from '@/components/modals/TaskStatusDialog.vue'
import type { TaskStatus } from '@/types/utils.ts'
import { useTheme } from 'vuetify'

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Флаг загрузки: переключает карточку в состояние скелетона. */
  loading: boolean
}

const props = defineProps<IProps>()

const theme = useTheme()
/** Вариант отображения чипов статуса: `flat` в тёмной теме, `tonal` в светлой. */
const chipVariant = computed(() => (theme.global.current.value.dark ? 'flat' : 'tonal'))

const districtDataStore = useDistrictDataStore()

/** Список маршрутов инженеров. */
const routes = computed<EngineerRoute[]>(() => districtDataStore.getRoutes)

/** Список инженеров района (для выбора цвета маршрута). */
const engineers = computed<Engineer[]>(() => districtDataStore.getDistrictEngineers)

/** Карта «id задачи → адрес». */
const taskAddressById = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const task of districtDataStore.getDistrictTasks) {
    if (task.address) map[task.id] = task.address
  }
  return map
})

/** Карта «id задачи → статус». */
const taskStatusById = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const task of districtDataStore.getDistrictTasks) {
    map[task.id] = task.status
  }
  return map
})

/**
 * Возвращает адрес остановки.
 *
 * @param stop Остановка маршрута.
 * @returns Адрес или `'-'`, если адрес не задан.
 */
const getStopAddress = (stop: RouteStop): string => {
  return taskAddressById.value[stop.task_id] ?? '-'
}

/**
 * Возвращает статус задачи остановки.
 *
 * @param stop Остановка маршрута.
 * @returns Статус или `null`, если задача не найдена.
 */
const getStopStatus = (stop: RouteStop): string | null => {
  return taskStatusById.value[stop.task_id] ?? null
}

/**
 * Проверяет, можно ли менять статус задачи остановки.
 * Статус нельзя менять у терминальных состояний.
 *
 * @param stop Остановка маршрута.
 * @returns `true`, если смена статуса допустима.
 */
const canChangeStatus = (stop: RouteStop): boolean => {
  const status = getStopStatus(stop)
  if (!status) return false
  return !isTerminalStatus(status as TaskStatus)
}

/** Двусторонняя привязка выбранных маршрутов к `districtDataStore.selectedRoutes`. */
const selected = computed({
  get: () => districtDataStore.selectedRoutes,
  set: (v: string[]) => (districtDataStore.selectedRoutes = v),
})

/**
 * Переключает выделение маршрута инженера.
 *
 * @param item Маршрут.
 */
const toggleSelect = (item: EngineerRoute) => {
  districtDataStore.toggleRouteSelection(item.engineer_id)
}

/**
 * Проверяет, выделен ли маршрут инженера.
 *
 * @param item Маршрут.
 * @returns `true`, если маршрут выделен.
 */
const isSelected = (item: EngineerRoute) => {
  return districtDataStore.isRouteSelected(item.engineer_id)
}

/** Колонки таблицы маршрутов. */
const routeHeaders = [
  { title: 'Показать на карте', key: 'select', width: 100, sortable: false, align: 'start' },
  { title: '#', key: 'index', width: 60, sortable: false, align: 'center' },
  { title: 'Инженер', key: 'engineer_name', width: 100, sortable: false, align: 'center' },
  { title: 'Транспорт', key: 'vehicle_type', width: 100, sortable: false, align: 'center' },
  { title: 'Остановок', key: 'stops_length', width: 50, sortable: false, align: 'center' },
  { title: 'Дистанция', key: 'total_distance_km', width: 100, sortable: false, align: 'center' },
  {
    title: 'Время в пути',
    key: 'total_travel_minutes',
    width: 50,
    sortable: false,
    align: 'center',
  },
] as const

/** Колонки вложенной таблицы остановок. */
const stopHeaders = [
  { title: '#', key: 'index', width: 60, sortable: false, align: 'center' },
  { title: 'Заявка', key: 'task_id', width: 160, sortable: false, align: 'center' },
  { title: 'Прибытие', key: 'arrival_time', width: 140, sortable: false, align: 'center' },
  { title: 'Время работы', key: 'service_time', width: 220, sortable: false, align: 'center' },
  { title: 'От предыдущего', key: 'from_previous', width: 200, sortable: false, align: 'center' },
  { title: 'Адрес', key: 'address', width: 240, sortable: false, align: 'start' },
  { title: 'Статус', key: 'status', width: 140, sortable: false, align: 'center' },
  { title: 'Действия', key: 'actions', width: 140, sortable: false, align: 'center' },
] as const

/**
 * Форматирует дистанцию.
 *
 * @param v Дистанция в километрах.
 * @returns Строка вида `«12.34 км»`.
 */
const formatKm = (v: number) => `${v.toFixed(2)} км`

/**
 * Форматирует время в минутах.
 *
 * @param v Время в минутах.
 * @returns Строка вида `«8 мин»`.
 */
const formatMin = (v: number) => `${v.toFixed(0)} мин`

// --- Состояние диалогов -----------------------------------------------------

/** Флаг открытия диалога объяснения. */
const explanationDialogOpened = ref<boolean>(false)
/** Флаг открытия диалога переназначения. */
const reassignmentDialogOpened = ref<boolean>(false)
/** Флаг открытия диалога изменения статуса. */
const statusDialogOpened = ref<boolean>(false)

/** Выбранная остановка для диалогов объяснения и переназначения. */
const selectedStop = ref<RouteStop | null>(null)
/** Выбранный маршрут для диалога объяснения. */
const selectedRoute = ref<EngineerRoute | null>(null)
/** Идентификатор задачи для диалога изменения статуса. */
const selectedStatusTaskId = ref<string | null>(null)

/**
 * Открывает диалог объяснения для остановки.
 *
 * @param stop  Остановка.
 * @param route Маршрут, которому принадлежит остановка.
 */
const openExplanationDialog = (stop: RouteStop, route: EngineerRoute) => {
  selectedStop.value = stop
  selectedRoute.value = route
  explanationDialogOpened.value = true
}

/** Закрывает диалог объяснения и очищает выбранные данные. */
const closeExplanationDialog = () => {
  explanationDialogOpened.value = false
  selectedStop.value = null
  selectedRoute.value = null
}

/**
 * Открывает диалог переназначения для остановки.
 *
 * @param stop  Остановка.
 * @param route Маршрут, которому принадлежит остановка.
 */
const openReassignmentDialog = (stop: RouteStop, route: EngineerRoute) => {
  selectedStop.value = stop
  selectedRoute.value = route
  reassignmentDialogOpened.value = true
}

/** Закрывает диалог переназначения и очищает выбранные данные. */
const closeReassignmentDialog = () => {
  reassignmentDialogOpened.value = false
  selectedStop.value = null
  selectedRoute.value = null
}

/**
 * Открывает диалог изменения статуса для остановки.
 *
 * @param stop Остановка.
 */
const openStatusDialog = (stop: RouteStop) => {
  selectedStatusTaskId.value = stop.task_id
  statusDialogOpened.value = true
}

/** Закрывает диалог изменения статуса и очищает выбранную задачу. */
const closeStatusDialog = () => {
  statusDialogOpened.value = false
  selectedStatusTaskId.value = null
}
</script>

<template>
  <basic-card :loading="props.loading" title="Полная информация о маршрутах">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>

    <v-data-table-virtual
      v-if="!props.loading"
      v-model="selected"
      class="routes-table"
      :items="routes.filter((item) => item.stops.length)"
      item-value="engineer_id"
      show-expand
      density="comfortable"
      :headers="routeHeaders"
    >
      <!-- Чекбокс выбора маршрута для отображения на карте -->
      <template #item.select="{ item }">
        <v-checkbox-btn
          :model-value="isSelected(item)"
          density="comfortable"
          hide-details
          :color="getEngineerColor(item.engineer_id, engineers)"
          @update:model-value="toggleSelect(item)"
        />
      </template>

      <template #item.index="{ index }">
        {{ index + 1 }}
      </template>

      <template #item.vehicle_type="{ item }">
        {{ getVehicleTypeTranslation(item.vehicle_type) }}
      </template>

      <template #item.stops_length="{ item }">
        {{ item.stops.length }}
      </template>

      <template #item.total_distance_km="{ item }">
        {{ formatKm(item.total_distance_km) }}
      </template>

      <template #item.total_travel_minutes="{ item }">
        {{ formatMin(item.total_travel_minutes) }}
      </template>

      <!-- Раскрытая строка: вложенная таблица остановок -->
      <template #expanded-row="{ columns, item }">
        <tr>
          <td :colspan="columns.length" class="pa-0" style="background: lightgray !important">
            <basic-card title="Остановки маршрута" class="ma-3">
              <v-data-table-virtual
                class="stops-table"
                :headers="stopHeaders"
                :items="item.stops"
                density="compact"
                item-value="task_id"
                style="min-width: 1140px !important"
              >
                <template #item.index="{ index }">
                  {{ index + 1 }}
                </template>

                <template #item.service_time="{ item }">
                  {{ item.service_start_time }} - {{ item.service_end_time }}
                </template>

                <template #item.from_previous="{ item }">
                  {{ formatMin(item.travel_time_from_previous) }} ({{
                    formatKm(item.distance_from_previous_km)
                  }})
                </template>

                <template #item.address="{ item }">
                  {{ getStopAddress(item) }}
                </template>

                <template #item.status="{ item }">
                  <v-chip
                    size="small"
                    :variant="chipVariant"
                    :color="getTaskStatusColor(getStopStatus(item))"
                  >
                    {{ getTaskStatusLabel(getStopStatus(item)) }}
                  </v-chip>
                </template>

                <template #item.actions="props">
                  <v-row no-gutters class="text-no-wrap justify-center">
                    <icon-button
                      icon="info"
                      color="blue"
                      tooltip-text="Причины назначения"
                      @click="openExplanationDialog(props.item, item)"
                    />
                    <icon-button
                      icon="transfer_within_a_station"
                      color="warning"
                      tooltip-text="Переназначить исполнителя"
                      @click="openReassignmentDialog(props.item, item)"
                    />
                    <icon-button
                      v-if="canChangeStatus(props.item)"
                      icon="published_with_changes"
                      color="primary"
                      tooltip-text="Изменить статус"
                      @click="openStatusDialog(props.item)"
                    />
                  </v-row>
                </template>
              </v-data-table-virtual>
            </basic-card>
          </td>
        </tr>
      </template>
    </v-data-table-virtual>

    <!-- Диалоги действий над остановкой -->
    <task-explanation-dialog
      :opened="explanationDialogOpened"
      :stop="selectedStop"
      :route="selectedRoute"
      @close="closeExplanationDialog"
    />
    <reasignment-dialog
      :opened="reassignmentDialogOpened"
      :task-id="selectedStop ? selectedStop.task_id : null"
      @close="closeReassignmentDialog"
    />
    <task-status-dialog
      :opened="statusDialogOpened"
      :task-id="selectedStatusTaskId"
      @close="closeStatusDialog"
    />
  </basic-card>
</template>

<style scoped lang="scss">
/**
 * Таблица маршрутов: предотвращает переполнение по горизонтали
 * и включает горизонтальную прокрутку для широкого контента.
 */
.routes-table :deep(.v-table__wrapper),
.routes-table :deep(.v-table__wrapper > table) {
  min-width: 0;
}

:deep(.v-table__wrapper) {
  overflow-x: auto !important;
}
</style>
