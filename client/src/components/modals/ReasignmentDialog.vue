<script setup lang="ts">
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, ref, watch } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import type { PreviewReassignmentObjectMetrics } from '@/types/entities.ts'
import { replaceSkillTypes } from '@/utils/translations.ts'

const emit = defineEmits<{
  close: []
}>()

interface IProps {
  opened: boolean
  taskId: string | null
}

const props = defineProps<IProps>()

type PreviewReassignmentFormData = {
  taskId: string | null
  engineerId: string | null
}

const defaultFormData: PreviewReassignmentFormData = {
  taskId: '',
  engineerId: null,
}

const formData = ref<PreviewReassignmentFormData>({ ...defaultFormData })

const store = useDistrictDataStore()
const loading = computed(() => store.loadingManualReassignment)
const loadingPreview = computed(() => store.loadingManualReassignmentPreview)
const engineersSelectorItems = computed(() => store.getDistrictEngineersSelector)
const previewObject = computed(() => store.manualReassignmentObject)

const getDialogTitle = computed(() => {
  if (!props.taskId) return ''
  return `Ручное переназначение заявки ${props.taskId}`
})

watch(
  () => props.opened,
  (nVal) => {
    if (!nVal) return
    store.clearManualReassignmentPreview()
    formData.value = {
      taskId: props.taskId,
      engineerId: null,
    }
  },
)

watch(
  () => formData.value.engineerId,
  (nVal) => {
    if (!nVal) {
      store.clearManualReassignmentPreview()
      return
    }
    preview()
  },
)

const preview = async () => {
  if (!formData.value.engineerId || !formData.value.taskId) return
  await store.loadManualReassignmentPreview({
    task_id: formData.value.taskId,
    engineer_id: formData.value.engineerId,
  })
}

const reassign = async () => {
  await store.loadManualReassignment()
  emit('close')
}

type MetricKey = keyof PreviewReassignmentObjectMetrics
type MetricRow = {
  key: MetricKey
  label: string
  before: string
  after: string
  delta: number
}

const metricLabels: Record<MetricKey, string> = {
  used_engineers_count: 'Задействовано инженеров',
  total_distance_km: 'Суммарный пробег, км',
}

const formatMetric = (key: MetricKey, value: number): string => {
  switch (key) {
    case 'total_distance_km':
      return `${value.toFixed(1)} км`
    case 'used_engineers_count':
    default:
      return String(value)
  }
}

const metricRows = computed<MetricRow[]>(() => {
  const p = previewObject.value
  if (!p || !p.feasible) return []
  return (Object.keys(p.before) as MetricKey[]).map((key) => ({
    key,
    label: metricLabels[key] ?? key,
    before: formatMetric(key, p.before[key]),
    after: formatMetric(key, p.after[key]),
    delta: p.delta[key],
  }))
})

const deltaColor = (value: number) => (value > 0 ? 'error' : value < 0 ? 'success' : undefined)

const deltaText = (value: number) => `${value > 0 ? '+' : ''}${value}`
</script>

<template>
  <v-dialog :model-value="props.opened" max-width="720" persistent>
    <basic-card :title="getDialogTitle" :show-bottom="true">
      <template #toolbarAppend>
        <icon-button
          icon="close"
          class="ml-3"
          :loading="loadingPreview || loading"
          @click="emit('close')"
          tooltip-text="Закрыть"
        />
      </template>

      <v-container class="overflow-list default-scrollbar px-4 py-4">
        <v-select
          v-model="formData.engineerId"
          :items="engineersSelectorItems"
          variant="outlined"
          label="Инженер"
          hide-details
          :readonly="loading"
          :loading="loadingPreview"
          :clearable="false"
        />

        <template v-if="!loadingPreview && previewObject">
          <v-alert v-if="!previewObject.feasible" type="error" class="mt-4" density="comfortable">
            {{ replaceSkillTypes(previewObject.message) }}
          </v-alert>

          <template v-else>
            <v-row no-gutters class="mt-4" align="center">
              <v-col cols="12" sm="5">
                <v-card color="warning" class="pa-3">
                  <v-card-subtitle class="text-body-large px-0">Старый инженер</v-card-subtitle>
                  <v-card-title class="text-body-1 font-weight-bold pa-0">
                    {{ previewObject.old_engineer.name }}
                  </v-card-title>
                </v-card>
              </v-col>

              <v-col cols="12" sm="2" class="d-flex justify-center">
                <v-icon icon="arrow_right" size="28" />
              </v-col>

              <v-col cols="12" sm="5">
                <v-card color="success" class="pa-3">
                  <v-card-subtitle class="text-body-large px-0">Новый инженер</v-card-subtitle>
                  <v-card-title class="text-body-1 font-weight-bold pa-0">
                    {{ previewObject.new_engineer.name }}
                  </v-card-title>
                </v-card>
              </v-col>
            </v-row>

            <v-data-table
              :items="metricRows"
              :headers="[
                { title: 'Метрика', key: 'label' },
                { title: 'До', key: 'before', align: 'end' },
                { title: 'После', key: 'after', align: 'end' },
                { title: 'Δ', key: 'delta', align: 'end' },
              ]"
              density="compact"
              hide-default-footer
              class="mt-4"
            >
              <template #item.delta="{ item }">
                <v-chip size="small" variant="tonal" :color="deltaColor(item.delta)">
                  {{ deltaText(item.delta) }}
                </v-chip>
              </template>
            </v-data-table>
          </template>
        </template>
      </v-container>

      <template #bottom>
        <v-row no-gutters class="justify-end pb-2">
          <v-btn
            color="primary"
            variant="flat"
            :loading="loadingPreview || loading"
            :disabled="!previewObject || !previewObject.feasible"
            @click="reassign"
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
  overflow-y: auto;
}
</style>
