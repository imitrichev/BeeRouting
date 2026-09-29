<script setup lang="ts">
/**
 * Диалог изменения статуса задачи.
 *
 * Позволяет перевести задачу в один из допустимых статусов согласно
 * `TASK_STATUS_TRANSITIONS`. Если задача входит в маршрут и предыдущие
 * остановки ещё не завершены, доступна только отмена (статус `CANCELLED`).
 * Для терминальных статусов изменение заблокировано.
 *
 * При подтверждении отправляет запрос через `districtDataStore.loadUpdateTaskStatus`
 * и закрывает диалог.
 */

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

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Флаг открытия диалога. */
  opened: boolean
  /** Идентификатор задачи (или `null`, если задача не выбрана). */
  taskId: string | null
}

const props = defineProps<IProps>()

/**
 * События компонента.
 */
const emit = defineEmits<{
  /** Закрытие диалога. */
  close: []
}>()

const store = useDistrictDataStore()

/** Флаг загрузки запроса обновления статуса. */
const loading = computed(() => store.loadingUpdateTaskStatus)

/** Задача, для которой открыт диалог (или `null`, если не найдена). */
const task = computed<Task | null>(() => {
  if (!props.taskId) return null
  return store.getDistrictTasks.find((t) => t.id === props.taskId) ?? null
})

/** Текущий статус задачи. */
const currentStatus = computed<TaskStatus | null>(() => {
  return (task.value?.status as TaskStatus) ?? null
})

/** Новый статус, выбранный пользователем. */
const selectedStatus = ref<TaskStatus | null>(null)

/** Карта задач по id для быстрого поиска при проверке предыдущих остановок. */
const taskMap = computed<Map<string, Task>>(() => {
  const map = new Map<string, Task>()
  for (const t of store.getDistrictTasks) map.set(t.id, t)
  return map
})

/** Маршрут, содержащий задачу, или `null`. */
const route = computed(() => {
  if (!props.taskId) return null
  return findRouteByTaskId(store.getRoutes, props.taskId)
})

/**
 * `true`, если изменение статуса заблокировано незавершёнными предыдущими
 * остановками маршрута.
 */
const isBlockedByRoute = computed<boolean>(() => {
  if (!route.value || !props.taskId) return false
  return !arePreviousStopsDone(route.value, props.taskId, taskMap.value)
})

/** Допустимые переходы с учётом блокировки по маршруту. */
const availableTransitions = computed<TaskStatus[]>(() => {
  if (!currentStatus.value) return []

  const all = getAvailableTransitions(currentStatus.value)

  if (isBlockedByRoute.value) {
    return all.filter((s) => s === 'CANCELLED')
  }

  return all
})

/** Элементы для `v-select`: значение + отображаемая метка. */
const transitionItems = computed(() =>
  availableTransitions.value.map((value) => ({
    value,
    title: TASK_STATUS_MAP[value],
  })),
)

/** `true`, если изменение статуса полностью заблокировано (терминальный/пустой). */
const isLocked = computed<boolean>(() => {
  if (!currentStatus.value) return true
  if (isTerminalStatus(currentStatus.value)) return true
  return availableTransitions.value.length === 0
})

/** При открытии диалога сбрасывает выбранный статус. */
watch(
  () => props.opened,
  (opened) => {
    if (opened) {
      selectedStatus.value = null
    }
  },
)

/**
 * Отправляет запрос на изменение статуса и закрывает диалог.
 * Ничего не делает, если задача/статус не выбраны или переход запрещён.
 */
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
  <v-dialog :model-value="props.opened" max-width="480" persistent>
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
          <!-- Предупреждение о блокировке предыдущими остановками -->
          <v-alert
            v-if="isBlockedByRoute && !isLocked"
            type="warning"
            variant="flat"
            class="w-100 mb-6"
          >
            Предыдущие заявки в маршруте ещё не выполнены. Доступна только отмена.
          </v-alert>

          <!-- Задача в терминальном статусе: изменение невозможно -->
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

          <!-- Выбор нового статуса (если не заблокировано) -->
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

        <!-- Задача не найдена -->
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
/**
 * Ограничивает высоту контента диалога 80% высоты вьюпорта
 * с вертикальной прокруткой при переполнении.
 */
.overflow-list {
  max-height: 80vh !important;
  min-height: unset !important;
}
</style>
