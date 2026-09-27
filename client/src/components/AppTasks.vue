<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import type { EngineerRoute, RouteStop, Task } from '@/types/entities.ts'
import {
  getPriorityTranslation,
  getSkillTranslation,
  getVehicleTypeTranslation,
} from '@/utils/translations.ts'
import { computed, ref } from 'vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import IconButton from '@/templates/IconButton.vue'
import TaskExplanationDialog from '@/components/modals/TaskExplanationDialog.vue'
import ReasignmentDialog from '@/components/modals/ReasignmentDialog.vue'
import { useTheme } from 'vuetify'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const theme = useTheme()
const chipVariant = computed(() => (theme.global.current.value.dark ? 'flat' : 'tonal'))

const districtDataStore = useDistrictDataStore()
const tasks = computed<Task[]>(() => districtDataStore.getDistrictTasks)

const result = computed(() => districtDataStore.getDistrictData?.result)
const isOptimized = computed(() => !!result.value)

const routes = computed<EngineerRoute[]>(() => districtDataStore.getRoutes)

const assignedTaskIds = computed<Set<string>>(() => {
  const ids = new Set<string>()
  for (const route of routes.value) {
    for (const stop of route.stops) {
      ids.add(stop.task_id)
    }
  }
  return ids
})

// --- заголовки ---
const baseHeaders = [
  { title: 'Заявка', key: 'id', width: 160, sortable: false, align: 'center' },
  { title: 'Тип', key: 'required_skill', width: 140, sortable: false, align: 'center' },
  { title: 'Окно', key: 'window', width: 200, sortable: false, align: 'center' },
  { title: 'Длит.', key: 'duration_minutes', width: 80, sortable: false, align: 'center' },
  { title: 'Приоритет', key: 'priority', width: 120, sortable: false, align: 'center' },
  {
    title: 'Необходимый транспорт',
    key: 'required_vehicle_type',
    width: 160,
    sortable: false,
    align: 'center',
  },
  {
    title: 'Требуемое оборудование',
    key: 'required_equipment',
    width: 200,
    sortable: false,
    align: 'center',
  },
  { title: 'Локация', key: 'location', width: 240, sortable: false, align: 'start' },
  { title: 'Статус', key: 'status', width: 160, sortable: false, align: 'center' },
  { title: 'Инженер', key: 'current_engineer_id', width: 160, sortable: false, align: 'center' },
]

const taskHeaders = computed(() => {
  if (!isOptimized.value) return baseHeaders
  return [
    ...baseHeaders,
    { title: 'Действия', key: 'actions', width: 120, sortable: false, align: 'center' },
  ]
})

const getPriorityColor = (priority: string): string => {
  return priority === 'URGENT' ? 'error' : 'default'
}

const STATUS_LABELS: Record<string, string> = {
  NOT_SENT: 'не отправлена',
  ASSIGNED: 'назначена',
  EN_ROUTE: 'в пути',
  IN_PROGRESS: 'в работе',
  COMPLETED: 'выполнена',
  CANCELLED: 'отменена',
  OVERDUE: 'просрочена',
}

function taskStatusLabel(task: Task): string {
  if (result.value && task.is_plannable) {
    if (['COMPLETED', 'CANCELLED', 'EN_ROUTE', 'IN_PROGRESS', 'OVERDUE'].includes(task.status)) {
      return String(STATUS_LABELS[task.status])
    }
    if (assignedTaskIds.value.has(task.id)) {
      return 'назначена в плане'
    }
    return 'не назначена'
  }
  return STATUS_LABELS[task.status] ?? task.status
}

function taskStatusColor(task: Task): string {
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

const engineerNameById = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const route of routes.value) {
    map[route.engineer_id] = route.engineer_name
  }
  return map
})

function engineerLabel(task: Task): string {
  if (!task.current_engineer_id) return '-'
  return engineerNameById.value[task.current_engineer_id] ?? task.current_engineer_id
}

function findStopAndRoute(taskId: string): { stop: RouteStop; route: EngineerRoute } | null {
  for (const route of routes.value) {
    const stop = route.stops.find((s) => s.task_id === taskId)
    if (stop) return { stop, route }
  }
  return null
}

const canOpenDialogs = (task: Task): boolean => {
  if (!isOptimized.value) return false
  return assignedTaskIds.value.has(task.id)
}

const explanationDialogOpened = ref(false)
const reassignmentDialogOpened = ref(false)
const selectedStop = ref<RouteStop | null>(null)
const selectedRoute = ref<EngineerRoute | null>(null)
const selectedTaskId = ref<string | null>(null)

const openExplanationDialog = (task: Task) => {
  const found = findStopAndRoute(task.id)
  if (!found) return
  selectedStop.value = found.stop
  selectedRoute.value = found.route
  explanationDialogOpened.value = true
}

const closeExplanationDialog = () => {
  explanationDialogOpened.value = false
  selectedStop.value = null
  selectedRoute.value = null
}

const openReassignmentDialog = (task: Task) => {
  selectedTaskId.value = task.id
  reassignmentDialogOpened.value = true
}

const closeReassignmentDialog = () => {
  reassignmentDialogOpened.value = false
  selectedTaskId.value = null
}
</script>

<template>
  <basic-card title="Заявки" :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>

    <v-data-table-virtual
      v-if="!props.loading"
      class="tasks-table"
      :headers="taskHeaders"
      :items="tasks"
      item-value="id"
      density="comfortable"
      height="300"
    >
      <template #item.required_skill="{ item }">
        {{ getSkillTranslation(item.required_skill) }}
      </template>

      <template #item.window="{ item }"> {{ item.window_start }} - {{ item.window_end }} </template>

      <template #item.duration_minutes="{ item }"> {{ item.duration_minutes }} мин </template>

      <template #item.priority="{ item }">
        <v-chip size="small" variant="tonal" :color="getPriorityColor(item.priority)">
          {{ getPriorityTranslation(item.priority) }}
        </v-chip>
      </template>

      <template #item.required_vehicle_type="{ item }">
        {{ getVehicleTypeTranslation(item.required_vehicle_type) }}
      </template>

      <template #item.required_equipment="{ item }">
        <template v-if="item.required_equipment.length">
          <v-chip
            v-for="eq in item.required_equipment"
            :key="eq"
            size="x-small"
            variant="tonal"
            class="ma-1"
          >
            {{ eq }}
          </v-chip>
        </template>
        <span v-else>-</span>
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
        </v-row>
        <span v-else>-</span>
      </template>
    </v-data-table-virtual>

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
  </basic-card>
</template>

<style scoped lang="scss">
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
