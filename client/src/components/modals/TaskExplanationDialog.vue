<script setup lang="ts">
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

const emit = defineEmits<{
  close: []
}>()

interface IProps {
  opened: boolean
  stop: RouteStop | null
  route: EngineerRoute | null
}

const props = defineProps<IProps>()

const store = useDistrictDataStore()
const loading = computed(() => store.loadingExplanation)
const explanation = computed(() => store.taskExplanation)

watch(
  () => (props.stop ? props.stop.task_id : undefined),
  (nVal) => {
    if (!nVal) return
    loadTaskExplanation(nVal)
  },
)

const getDialogTitle = computed((): string => {
  if (!props.stop) return ''
  const engineerName = props.route?.engineer_name
  return engineerName
    ? `Причины назначения заявки ${props.stop.task_id} инженеру ${engineerName}`
    : `Причины неназначения заявки ${props.stop.task_id}`
})

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
.overflow-list {
  max-height: 80vh !important;
  min-height: unset !important;
}
</style>
