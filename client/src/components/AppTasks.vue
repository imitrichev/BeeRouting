<script setup lang="ts">
/**
 * Таблица заявок (задач) района.
 *
 * Отображает список задач с колонками: идентификатор, тип (навык), временное
 * окно, длительность, приоритет, требуемое число роутеров, локация, статус
 * и назначенный инженер.
 *
 * После оптимизации:
 * - добавляется колонка «Действия» с кнопками «объяснение», «переназначить»
 *   и «изменить статус»;
 * - статус задач пересчитывается относительно плана (назначена / не назначена).
 *
 * В шапке карточки доступна кнопка создания заявки.
 */

import type { DataTableHeader } from 'vuetify'
import BasicCard from '@/templates/BasicCard.vue'
import type { EngineerRoute, RouteStop, Task } from '@/types/entities.ts'
import { getPriorityTranslation, getSkillTranslation } from '@/utils/translations.ts'
import { computed, ref } from 'vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import IconButton from '@/templates/IconButton.vue'
import TaskExplanationDialog from '@/components/modals/TaskExplanationDialog.vue'
import ReasignmentDialog from '@/components/modals/ReasignmentDialog.vue'
import { useTheme } from 'vuetify'
import TaskCreateDialog from '@/components/modals/TaskCreateDialog.vue'
import type { TaskStatus } from '@/types/utils.ts'
import TaskStatusDialog from '@/components/modals/TaskStatusDialog.vue'
import { isTerminalStatus } from '@/utils/task.ts'
import { getTaskStatusLabel } from '@/utils/task.ts'

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

/** Список задач района. */
const tasks = computed<Task[]>(() => districtDataStore.getDistrictTasks)

/** Результат оптимизации (или `undefined`, если расчёт ещё не выполнялся). */
const result = computed(() => districtDataStore.getDistrictData?.result)

/** `true`, если для текущего района есть результат оптимизации. */
const isOptimized = computed(() => !!result.value)

/** Маршруты инженеров из результата оптимизации. */
const routes = computed<EngineerRoute[]>(() => districtDataStore.getRoutes)

/** Множество идентификаторов задач, попавших в маршруты. */
const assignedTaskIds = computed<Set<string>>(() => {
  const ids = new Set<string>()
  for (const route of routes.value) {
    for (const stop of route.stops) {
      ids.add(stop.task_id)
    }
  }
  return ids
})

/**
 * Базовые колонки таблицы (без колонки действий).
 * Колонка «Действия» добавляется после оптимизации.
 */
const baseHeaders: DataTableHeader[] = [
  { title: 'Заявка', key: 'id', width: 160, sortable: true, align: 'center' },
  { title: 'Тип', key: 'required_skill', width: 140, sortable: true, align: 'center' },
  { title: 'Окно', key: 'window_start', width: 200, sortable: true, align: 'center' },
  { title: 'Длит.', key: 'duration_minutes', width: 80, sortable: true, align: 'center' },
  { title: 'Приоритет', key: 'priority', width: 120, sortable: true, align: 'center' },
  {
    title: 'Необходимо роутеров',
    key: 'required_router_count',
    width: 160,
    sortable: true,
    align: 'center',
  },
  { title: 'Локация', key: 'location', width: 240, sortable: false, align: 'start' },
  { title: 'Статус', key: 'status', width: 160, sortable: true, align: 'center' },
  { title: 'Инженер', key: 'current_engineer_id', width: 160, sortable: true, align: 'center' },
]

/** Полный набор колонок таблицы (с колонкой действий после оптимизации). */
const taskHeaders = computed((): DataTableHeader[] => {
  if (!isOptimized.value) return baseHeaders
  return [
    ...baseHeaders,
    { title: 'Действия', key: 'actions', width: 200, sortable: false, align: 'center' },
  ]
})

/**
 * Возвращает цвет чипа приоритета.
 *
 * @param priority Код приоритета.
 * @returns `'error'` для срочного, `'default'` для остальных.
 */
const getPriorityColor = (priority: string): string => {
  return priority === 'URGENT' ? 'error' : 'default'
}

/**
 * Возвращает метку статуса задачи с учётом результата оптимизации.
 *
 * Если расчёт выполнен и задача планируемая:
 * - для активных/терминальных статусов возвращается стандартная метка;
 * - «назначена в плане», если задача попала в маршрут;
 * - «не назначена» в противном случае.
 *
 * @param task Задача.
 * @returns Метка статуса.
 */
const taskStatusLabel = (task: Task): string => {
  if (result.value && task.is_plannable) {
    if (['COMPLETED', 'CANCELLED', 'EN_ROUTE', 'IN_PROGRESS', 'OVERDUE'].includes(task.status)) {
      return getTaskStatusLabel(task.status)
    }
    if (assignedTaskIds.value.has(task.id)) {
      return 'назначена в плане'
    }
    return 'не назначена'
  }
  return getTaskStatusLabel(task.status)
}

/**
 * Возвращает цвет чипа статуса задачи с учётом результата оптимизации.
 * Неназначенные планируемые задачи подсвечиваются как ошибка.
 *
 * @param task Задача.
 * @returns Токен цвета Vuetify.
 */
const taskStatusColor = (task: Task): string => {
  if (result.value && task.is_plannable && !assignedTaskIds.value.has(task.id)) return 'error'
  return (
    {
      NOT_SENT: 'grey',
      ASSIGNED: 'indigo',
      EN_ROUTE: 'cyan-darken-1',
      IN_PROGRESS: 'blue-darken-1',
      COMPLETED: 'success',
      CANCELLED: 'grey-darken-1',
      OVERDUE: 'error',
    }[task.status] ?? 'grey'
  )
}

/** Карта «id инженера → имя инженера» на основе маршрутов. */
const engineerNameById = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const route of routes.value) {
    map[route.engineer_id] = route.engineer_name
  }
  return map
})

/**
 * Возвращает имя инженера, назначенного на задачу, либо `'-'`.
 *
 * @param task Задача.
 * @returns Имя инженера или `'-'`.
 */
const engineerLabel = (task: Task): string => {
  if (!task.current_engineer_id) return '-'
  return engineerNameById.value[task.current_engineer_id] ?? task.current_engineer_id
}

/**
 * Находит остановку и маршрут, содержащие указанную задачу.
 *
 * @param taskId Идентификатор задачи.
 * @returns Объект `{ stop, route }` или `null`, если задача не в маршрутах.
 */
const findStopAndRoute = (taskId: string): { stop: RouteStop; route: EngineerRoute } | null => {
  for (const route of routes.value) {
    const stop = route.stops.find((s) => s.task_id === taskId)
    if (stop) return { stop, route }
  }
  return null
}

/**
 * Проверяет, доступны ли действия для задачи.
 * Действия доступны только после оптимизации и только для назначенных задач.
 *
 * @param task Задача.
 * @returns `true`, если для задачи можно открывать диалоги действий.
 */
const canOpenDialogs = (task: Task): boolean => {
  if (!isOptimized.value) return false
  return assignedTaskIds.value.has(task.id)
}

// --- Состояние диалогов -----------------------------------------------------

/** Флаг открытия диалога объяснения. */
const explanationDialogOpened = ref(false)
/** Флаг открытия диалога переназначения. */
const reassignmentDialogOpened = ref(false)
/** Выбранная остановка для диалога объяснения. */
const selectedStop = ref<RouteStop | null>(null)
/** Выбранный маршрут для диалога объяснения. */
const selectedRoute = ref<EngineerRoute | null>(null)
/** Идентификатор выбранной задачи для диалогов переназначения и статуса. */
const selectedTaskId = ref<string | null>(null)

/**
 * Открывает диалог объяснения для задачи.
 * Ничего не делает, если задача не найдена среди остановок маршрутов.
 *
 * @param task Задача.
 */
const openExplanationDialog = (task: Task) => {
  const found = findStopAndRoute(task.id)
  if (!found) return
  selectedStop.value = found.stop
  selectedRoute.value = found.route
  explanationDialogOpened.value = true
}

/** Закрывает диалог объяснения и очищает выбранные данные. */
const closeExplanationDialog = () => {
  explanationDialogOpened.value = false
  selectedStop.value = null
  selectedRoute.value = null
}

/**
 * Открывает диалог переназначения для задачи.
 *
 * @param task Задача.
 */
const openReassignmentDialog = (task: Task) => {
  selectedTaskId.value = task.id
  reassignmentDialogOpened.value = true
}

/** Закрывает диалог переназначения и очищает выбранную задачу. */
const closeReassignmentDialog = () => {
  reassignmentDialogOpened.value = false
  selectedTaskId.value = null
}

/** Флаг открытия диалога создания задачи. */
const createTaskDialogOpened = ref(false)

/** Открывает диалог создания задачи. */
const openCreateTaskDialog = () => {
  createTaskDialogOpened.value = true
}

/** Закрывает диалог создания задачи. */
const closeCreateTaskDialog = () => {
  createTaskDialogOpened.value = false
}

/** Флаг открытия диалога изменения статуса. */
const statusDialogOpened = ref(false)
/** Идентификатор задачи, для которой меняется статус. */
const selectedStatusTaskId = ref<string | null>(null)

/**
 * Открывает диалог изменения статуса для задачи.
 *
 * @param task Задача.
 */
const openStatusDialog = (task: Task) => {
  selectedStatusTaskId.value = task.id
  statusDialogOpened.value = true
}

/** Закрывает диалог изменения статуса и очищает выбранную задачу. */
const closeStatusDialog = () => {
  statusDialogOpened.value = false
  selectedStatusTaskId.value = null
}
</script>

<template>
  <basic-card title="Заявки" :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <template #toolbarAppend>
      <icon-button tooltip-text="Добавить заявку" @click="openCreateTaskDialog" />
    </template>

    <v-data-table-virtual
      v-if="!props.loading"
      class="tasks-table"
      :headers="taskHeaders"
      :items="tasks"
      item-value="id"
      density="comfortable"
      height="400"
    >
      <template #item.required_skill="{ item }">
        {{ getSkillTranslation(item.required_skill) }}
      </template>

      <template #item.window_start="{ item }">
        {{ item.window_start }} - {{ item.window_end }}
      </template>

      <template #item.duration_minutes="{ item }"> {{ item.duration_minutes }} мин </template>

      <template #item.priority="{ item }">
        <v-chip size="small" variant="tonal" :color="getPriorityColor(item.priority)">
          {{ getPriorityTranslation(item.priority) }}
        </v-chip>
      </template>

      <template #item.required_router_count="{ item }">
        {{ item.required_router_count }}
      </template>

      <template #item.location="{ item }">
        {{ item.address || '-' }}
      </template>

      <template #item.status="{ item }">
        <v-chip size="small" :variant="chipVariant" :color="taskStatusColor(item)">
          {{ taskStatusLabel(item) }}
        </v-chip>
      </template>

      <template #item.current_engineer_id="{ item }">
        {{ engineerLabel(item) }}
      </template>

      <!-- Действия: доступны только для назначенных задач после оптимизации -->
      <template #item.actions="{ item }">
        <v-row v-if="canOpenDialogs(item)" no-gutters class="text-no-wrap justify-center">
          <icon-button
            icon="info"
            color="blue"
            tooltip-text="Запросить объяснение"
            @click="openExplanationDialog(item)"
          />
          <icon-button
            v-if="!!item.current_engineer_id"
            icon="transfer_within_a_station"
            color="warning"
            tooltip-text="Переназначить исполнителя"
            @click="openReassignmentDialog(item)"
          />
          <icon-button
            v-if="!isTerminalStatus(item.status as TaskStatus)"
            icon="published_with_changes"
            color="primary"
            tooltip-text="Изменить статус"
            @click="openStatusDialog(item)"
          />
        </v-row>
        <span v-else>-</span>
      </template>
    </v-data-table-virtual>

    <!-- Диалоги действий над задачей -->
    <task-explanation-dialog
      :opened="explanationDialogOpened"
      :stop="selectedStop"
      :route="selectedRoute"
      @close="closeExplanationDialog"
    />
    <reasignment-dialog
      :opened="reassignmentDialogOpened"
      :task-id="selectedTaskId"
      @close="closeReassignmentDialog"
    />
    <task-create-dialog :opened="createTaskDialogOpened" @close="closeCreateTaskDialog" />
    <task-status-dialog
      :opened="statusDialogOpened"
      :task-id="selectedStatusTaskId"
      @close="closeStatusDialog"
    />
  </basic-card>
</template>

<style scoped lang="scss">
/**
 * Таблица заявок: предотвращает переполнение по горизонтали,
 * включает двустороннюю прокрутку и закрепляет шапку при скролле.
 */
.tasks-table :deep(.v-table__wrapper),
.tasks-table :deep(.v-table__wrapper > table) {
  min-width: 0;
}

:deep(.v-table__wrapper) {
  overflow-x: auto !important;
  overflow-y: auto !important;
  scrollbar-gutter: stable;
}

.tasks-table :deep(thead th) {
  position: sticky;
  top: 0;
  z-index: 2;
  background: rgb(var(--v-theme-surface));
}
</style>
