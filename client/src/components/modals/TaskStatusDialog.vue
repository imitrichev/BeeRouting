<script setup lang="ts">
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, ref, watch } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import type { Task, TaskStatusUpdateRequestData } from '@/types/entities.ts'
import { TASK_STATUS_MAP } from '@/utils/consts.ts'
import {
  arePreviousStopsDone,
  findRouteByTaskId,
  getAvailableTransitions,
  isTerminalStatus,
} from '@/utils/task.ts'
import type { TaskStatus } from '@/types/utils.ts'

interface IProps {
  opened: boolean
  taskId: string | null
}

const props = defineProps<IProps>()

const emit = defineEmits<{
  close: []
}>()

const store = useDistrictDataStore()
const loading = computed(() => store.loadingUpdateTaskStatus)

const task = computed<Task | null>(() => {
  if (!props.taskId) return null
  return store.getDistrictTasks.find((t) => t.id === props.taskId) ?? null
})

const currentStatus = computed<TaskStatus | null>(() => {
  return (task.value?.status as TaskStatus) ?? null
})

const selectedStatus = ref<TaskStatus | null>(null)

const taskMap = computed<Map<string, Task>>(() => {
  const map = new Map<string, Task>()
  for (const t of store.getDistrictTasks) map.set(t.id, t)
  return map
})

const route = computed(() => {
  if (!props.taskId) return null
  return findRouteByTaskId(store.getRoutes, props.taskId)
})

/**
 * Полноценное изменение статуса заблокировано, потому что
 * предыдущие заявки в маршруте ещё не выполнены/не отменены.
 */
const isBlockedByRoute = computed<boolean>(() => {
  if (!route.value || !props.taskId) return false
  return !arePreviousStopsDone(route.value, props.taskId, taskMap.value)
})

const availableTransitions = computed<TaskStatus[]>(() => {
  if (!currentStatus.value) return []

  const all = getAvailableTransitions(currentStatus.value)

  if (isBlockedByRoute.value) {
    return all.filter((s) => s === 'CANCELLED')
  }

  return all
})

const transitionItems = computed(() =>
  availableTransitions.value.map((value) => ({
    value,
    title: TASK_STATUS_MAP[value],
  })),
)

const isLocked = computed<boolean>(() => {
  if (!currentStatus.value) return true
  if (isTerminalStatus(currentStatus.value)) return true
  return availableTransitions.value.length === 0
})

watch(
  () => props.opened,
  (opened) => {
    if (opened) {
      selectedStatus.value = null
    }
  },
)

const updateStatus = async () => {
  if (!props.taskId || !selectedStatus.value) return
  if (isBlockedByRoute.value && selectedStatus.value !== 'CANCELLED') return

  const data: TaskStatusUpdateRequestData = {
    task_id: props.taskId,
    status: selectedStatus.value,
  }

  await store.loadUpdateTaskStatus(data)
  emit('close')
}
</script>

<template>
  <v-dialog :model-value="props.opened" max-width="480">
    <basic-card title="Изменение статуса заявки" :show-bottom="true">
      <template #toolbarAppend>
        <icon-button
          icon="close"
          class="ml-3"
          :loading="loading"
          @click="emit('close')"
          tooltip-text="Закрыть"
        />
      </template>

      <v-row no-gutters class="overflow-list default-scrollbar px-4 py-4">
        <template v-if="task">
          <v-alert
            v-if="isBlockedByRoute && !isLocked"
            type="warning"
            variant="flat"
            class="w-100 mb-6"
          >
            Предыдущие заявки в маршруте ещё не выполнены. Доступна только отмена.
          </v-alert>

          <v-alert v-if="isLocked" type="warning" variant="flat" class="w-100 mb-3">
            Статус этой заявки изменить нельзя.
          </v-alert>

          <v-text-field
            :model-value="task.id"
            variant="outlined"
            label="Заявка"
            class="w-100 mb-3"
            readonly
          />

          <v-text-field
            :model-value="currentStatus ? TASK_STATUS_MAP[currentStatus] : '-'"
            variant="outlined"
            label="Текущий статус"
            class="w-100 mb-3"
            readonly
          />

          <v-select
            v-if="!isLocked"
            v-model="selectedStatus"
            :items="transitionItems"
            variant="outlined"
            label="Новый статус"
            class="w-100"
            :readonly="loading"
            :clearable="false"
          />
        </template>

        <v-alert v-else type="error" variant="tonal" class="w-100"> Заявка не найдена. </v-alert>
      </v-row>

      <template #bottom>
        <v-row no-gutters class="justify-end pb-2">
          <v-btn
            :loading="loading"
            color="primary"
            variant="flat"
            class="text-none"
            :disabled="isLocked || !selectedStatus"
            @click="updateStatus"
          >
            Подтвердить
          </v-btn>
        </v-row>
      </template>
    </basic-card>
  </v-dialog>
</template>

<style scoped lang="scss">
.overflow-list {
  max-height: 80vh !important;
  min-height: unset !important;
}
</style>
