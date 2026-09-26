<script setup lang="ts">
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, ref, watch } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import type { OptimizationRequestData } from '@/types/entities.ts'

const emit = defineEmits<{
  close: []
}>()

interface IProps {
  opened: boolean
}

const props = defineProps<IProps>()

const defaultFormData: OptimizationRequestData = {
  consider_equipment: true,
  ignore_task_statuses: true,
  planning_time: null,
  solver: 'ortools',
}

const formData = ref<OptimizationRequestData>({ ...defaultFormData })

const store = useDistrictDataStore()
const loading = computed(() => store.loadingOptimization)

const solverSelectorItems = [
  {
    title: 'OR-Tools',
    value: 'ortools',
  },
  {
    title: 'Жёсткий (baseline)',
    value: 'baseline',
  },
]

watch(
  () => props.opened,
  (nVal) => {
    if (!nVal) return
    formData.value = defaultFormData
  },
)

const optimize = async () => {
  await store.optimizeDataset(formData.value)
  emit('close')
}
</script>

<template>
  <v-dialog :model-value="props.opened" max-width="600">
    <basic-card title="Распределение заявок" :show-bottom="true">
      <template #toolbarAppend>
        <icon-button
          icon="close"
          class="ml-3"
          :loading="loading"
          @click="emit('close')"
          tooltip-text="Закрыть"
        />
      </template>
      <v-row no-gutters class="overflow-list px-4 py-4">
        <v-select
          v-model="formData.solver"
          :items="solverSelectorItems"
          variant="outlined"
          label="Алгоритм"
          class="w-100"
          hide-details
          :readonly="loading"
          :clearable="false"
        />
        <v-checkbox
          v-model="formData.consider_equipment"
          label="Учитывать оборудование"
          class="mt-3"
          hide-details
          :readonly="loading"
        />
      </v-row>
      <template #bottom>
        <v-row no-gutters class="justify-end pb-2">
          <v-btn :loading="loading" @click="optimize"> Подтвердить </v-btn>
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
