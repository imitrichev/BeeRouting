<script setup lang="ts">
/**
 * Диалог запуска оптимизации распределения заявок.
 *
 * Позволяет выбрать алгоритм (`ortools` или `baseline`) и опцию
 * «учитывать оборудование». Остальные параметры запроса
 * (`ignore_task_statuses`, `planning_time`) зафиксированы дефолтами.
 *
 * При подтверждении вызывает `store.optimizeDataset(...)` и закрывает диалог.
 */

import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, ref, watch } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import type { OptimizationRequestData } from '@/types/entities.ts'

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
}

const props = defineProps<IProps>()

/** Значения формы по умолчанию. */
const defaultFormData: OptimizationRequestData = {
  consider_equipment: true,
  ignore_task_statuses: true,
  planning_time: null,
  solver: 'ortools',
}

/** Данные формы оптимизации. */
const formData = ref<OptimizationRequestData>({ ...defaultFormData })

const store = useDistrictDataStore()

/** Флаг загрузки запроса оптимизации. */
const loading = computed(() => store.loadingOptimization)

/** Элементы селектора алгоритмов. */
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

/** При открытии диалога сбрасывает форму к значениям по умолчанию. */
watch(
  () => props.opened,
  (nVal) => {
    if (!nVal) return
    formData.value = defaultFormData
  },
)

/**
 * Запускает оптимизацию с текущими параметрами формы и закрывает диалог.
 */
const optimize = async () => {
  await store.optimizeDataset(formData.value)
  emit('close')
}
</script>

<template>
  <v-dialog :model-value="props.opened" max-width="600" persistent>
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

      <v-row no-gutters class="overflow-list default-scrollbar px-4 py-4">
        <!-- Выбор алгоритма -->
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

        <!-- Опция: учитывать оборудование -->
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
          <v-btn
            :loading="loading"
            color="primary"
            variant="flat"
            class="text-none"
            @click="optimize"
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
