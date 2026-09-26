<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, ref } from 'vue'
import type { EngineerRoute } from '@/types/entities.ts'
import { getVehicleTypeTranslation } from '@/utils/translations.ts'
import { getEngineerColor } from '@/utils/map.ts'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()
const routes = computed<EngineerRoute[]>(() => districtDataStore.getRoutes)

const selected = computed({
  get: () => districtDataStore.selectedRoutes,
  set: (v: string[]) => (districtDataStore.selectedRoutes = v),
})

function toggleSelect(item: EngineerRoute) {
  districtDataStore.toggleRouteSelection(item.engineer_id)
}

function isSelected(item: EngineerRoute) {
  return districtDataStore.isRouteSelected(item.engineer_id)
}

const routeHeaders = [
  { title: 'Показать на карте', key: 'select', width: 100 },
  { title: '#', key: 'index', width: 60, sortable: false },
  { title: 'Инженер', key: 'engineer_name', width: 220 },
  { title: 'Транспорт', key: 'vehicle_type', width: 180 },
  { title: 'Остановок', key: 'stops_length', width: 120 },
  { title: 'Дистанция', key: 'total_distance_km', width: 140 },
  { title: 'Время в пути', key: 'total_travel_minutes', width: 160 },
]

const stopHeaders = [
  { title: '#', key: 'index', width: 60, sortable: false },
  { title: 'Задача', key: 'task_id', width: 160 },
  { title: 'Прибытие', key: 'arrival_time', width: 140 },
  { title: 'Начало', key: 'service_start_time', width: 140 },
  { title: 'Окончание', key: 'service_end_time', width: 140 },
  { title: 'В пути от пред.', key: 'travel_time_from_previous', width: 160 },
  { title: 'Расстояние от пред.', key: 'distance_from_previous_km', width: 180 },
  { title: 'Координаты', key: 'coordinates', width: 200, sortable: false },
]

const formatKm = (v: number) => `${v.toFixed(2)} км`
const formatMin = (v: number) => `${v.toFixed(0)} мин`
</script>

<template>
  <basic-card :loading="props.loading" title="Маршруты">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <v-data-table-virtual
      v-model="selected"
      class="routes-table"
      :items="routes.filter((item) => item.stops.length)"
      item-value="engineer_id"
      show-expand
      expand-strategy="single"
      density="comfortable"
      :headers="routeHeaders"
    >
      <template #item.select="{ item }">
        <v-checkbox-btn
          :model-value="isSelected(item)"
          density="comfortable"
          hide-details
          :color="getEngineerColor(item.engineer_id)"
          @update:model-value="toggleSelect(item)"
        />
      </template>
      <template #item.index="{ index }">
        {{ index + 1 }}
      </template>
      <template #item.vehicle_type="{ item }">
        {{ getVehicleTypeTranslation(item.vehicle_type) }}
      </template>
      <template #item.stops_length="{ item }">
        {{ item.stops.length }}
      </template>
      <template #item.total_distance_km="{ item }">
        {{ formatKm(item.total_distance_km) }}
      </template>
      <template #item.total_travel_minutes="{ item }">
        {{ formatMin(item.total_travel_minutes) }}
      </template>

      <template #expanded-row="{ columns, item }">
        <tr>
          <td :colspan="columns.length" class="pa-0">
            <v-card flat color="#DDD" class="px-3 py-4">
              <v-card-text class="pt-0 pl-1 text-body-large font-weight-bold">
                Остановки маршрута ({{ item.stops.length }})
              </v-card-text>

              <v-data-table-virtual
                class="stops-table"
                :headers="stopHeaders"
                :items="item.stops"
                density="compact"
                item-value="task_id"
              >
                <template #item.index="{ index }">
                  {{ index + 1 }}
                </template>

                <template #item.travel_time_from_previous="{ item }">
                  {{ formatMin(item.travel_time_from_previous) }}
                </template>

                <template #item.distance_from_previous_km="{ item }">
                  {{ formatKm(item.distance_from_previous_km) }}
                </template>

                <template #item.coordinates="{ item }">
                  <span v-if="item.latitude && item.longitude">
                    {{ item.latitude.toFixed(4) }}, {{ item.longitude.toFixed(4) }}
                  </span>
                  <span v-else>—</span>
                </template>
              </v-data-table-virtual>
            </v-card>
          </td>
        </tr>
      </template>
    </v-data-table-virtual>
  </basic-card>
</template>

<style scoped lang="scss">
.routes-table :deep(.v-table__wrapper),
.routes-table :deep(.v-table__wrapper > table) {
  min-width: 0;
}

:deep(.v-table__wrapper) {
  overflow-x: auto !important;
}
</style>
