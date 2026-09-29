<script setup lang="ts">
/**
 * Диалог с пояснением причин назначения (или неназначения) заявки.
 *
 * При открытии и смене выбранной остановки запрашивает у стора пояснение
 * (`store.loadTaskExplanation`). Текст пояснения проходит через цепочку
 * замен кодов справочников (типы работ, навыки, приоритеты, типы транспорта)
 * на их человекочитаемые подписи.
 *
 * Заголовок диалога зависит от того, назначена ли задача инженеру:
 * - «Причины назначения заявки … инженеру …» — если маршрут задан;
 * - «Причины неназначения заявки …» — в противном случае.
 */

import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, watch } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import type { EngineerRoute, RouteStop } from '@/types/entities.ts'
import {
  replacePriorityTypes,
  replaceSkillTypes,
  replaceVehicleTypes,
  replaceWorkTypes,
} from '@/utils/translations.ts'

/**
 * События компонента.
 */
const emit = defineEmits<{
  /** Закрытие диалога. */
  close: []
}>()

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Флаг открытия диалога. */
  opened: boolean
  /** Остановка маршрута, для которой запрашивается пояснение. */
  stop: RouteStop | null
  /** Маршрут, которому принадлежит остановка (если задача назначена). */
  route: EngineerRoute | null
}

const props = defineProps<IProps>()

const store = useDistrictDataStore()

/** Флаг загрузки пояснения. */
const loading = computed(() => store.loadingExplanation)

/** Текущее пояснение к остановке. */
const explanation = computed(() => store.taskExplanation)

/**
 * При смене идентификатора остановки запрашивает пояснение.
 * Игнорирует пустые значения.
 */
watch(
  () => (props.stop ? props.stop.task_id : undefined),
  (nVal) => {
    if (!nVal) return
    loadTaskExplanation(nVal)
  },
)

/** Заголовок диалога с учётом назначения задачи. */
const getDialogTitle = computed((): string => {
  if (!props.stop) return ''
  const engineerName = props.route?.engineer_name
  return engineerName
    ? `Причины назначения заявки ${props.stop.task_id} инженеру ${engineerName}`
    : `Причины неназначения заявки ${props.stop.task_id}`
})

/**
 * Запрашивает пояснение для указанной задачи через стор.
 *
 * @param taskId Идентификатор задачи.
 */
const loadTaskExplanation = (taskId: string) => {
  store.loadTaskExplanation(taskId)
}
</script>

<template>
  <v-dialog :model-value="opened" max-width="800" persistent>
    <basic-card :loading="loading" :title="getDialogTitle">
      <template #loading>
        <v-skeleton-loader type="article" />
      </template>
      <template #toolbarAppend>
        <icon-button icon="close" class="ml-3" @click="emit('close')" tooltip-text="Закрыть" />
      </template>

      <!-- Пояснение с заменами кодов справочников на подписи -->
      <v-row
        no-gutters
        v-if="!loading && explanation"
        class="overflow-list default-scrollbar px-4 py-4"
      >
        {{
          replaceWorkTypes(
            replaceSkillTypes(replacePriorityTypes(replaceVehicleTypes(explanation.explanation))),
          )
        }}
      </v-row>
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
