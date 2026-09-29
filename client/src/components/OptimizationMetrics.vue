<script setup lang="ts">
/**
 * Карточка с агрегированными метриками оптимизации распределения.
 *
 * Отображает четыре показателя: количество задействованных инженеров,
 * количество назначенных задач, суммарный пробег (км) и значение целевой
 * функции. Данные берутся из `districtDataStore.getMetrics`.
 *
 * Если метрики отсутствуют или идёт загрузка — вместо сетки показывается
 * скелетон.
 */

import BasicCard from '@/templates/BasicCard.vue'

import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed } from 'vue'

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Флаг загрузки: переключает карточку в состояние скелетона. */
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()

/** Агрегированные метрики оптимизации (или `null`, если расчёт не выполнялся). */
const metrics = computed(() => districtDataStore.getMetrics)
</script>

<template>
  <basic-card :loading="props.loading" title="Метрики распределения">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>

    <!-- Сетка метрик: 4 плитки, по 2 в ряд на узких экранах и по 4 на широких -->
    <v-row no-gutters v-if="metrics && !props.loading">
      <v-col cols="6" lg="3" class="fill-height">
        <v-card color="blue-lighten-4 fill-height" class="rounded-0 elevation-0" variant="flat">
          <v-card-text class="px-3 py-2">
            Инженеров: <br />
            <strong>{{ metrics.used_engineers_count }}</strong>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="6" lg="3" class="fill-height">
        <v-card color="green-lighten-4 fill-height" class="rounded-0 elevation-0" variant="flat">
          <v-card-text class="px-3 py-2">
            Задач: <br />
            <strong>{{ metrics.assigned_task_count }}</strong>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="6" lg="3" class="fill-height">
        <v-card color="red-lighten-4 fill-height" class="rounded-0 elevation-0" variant="flat">
          <v-card-text class="px-3 py-2">
            Пробег, км: <br />
            <strong>{{ metrics.total_distance_km.toFixed(1) }}</strong>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="6" lg="3" class="fill-height">
        <v-card color="purple-lighten-4 fill-height" class="rounded-0 elevation-0" variant="flat">
          <v-card-text class="px-3 py-2">
            Objective: <br />
            <strong>{{ metrics.total_objective }}</strong>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </basic-card>
</template>

<style scoped lang="scss"></style>
