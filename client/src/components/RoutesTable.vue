<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, ref } from 'vue'
import type { EngineerRoute, RouteStop } from '@/types/entities.ts'
import { getVehicleTypeTranslation } from '@/utils/translations.ts'
import { getEngineerColor } from '@/utils/map.ts'
import IconButton from '@/templates/IconButton.vue'
import TaskExplanationDialog from '@/components/modals/TaskExplanationDialog.vue'
import ReasignmentDialog from '@/components/modals/ReasignmentDialog.vue'
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
  { title: 'Показать на карте', key: 'select', width: 100, sortable: false, align: 'start' },
  { title: '#', key: 'index', width: 60, sortable: false, align: 'center' },
  { title: 'Инженер', key: 'engineer_name', width: 100, sortable: false, align: 'center' },
  { title: 'Транспорт', key: 'vehicle_type', width: 100, sortable: false, align: 'center' },
  { title: 'Остановок', key: 'stops_length', width: 50, sortable: false, align: 'center' },
  { title: 'Дистанция', key: 'total_distance_km', width: 100, sortable: false, align: 'center' },
  {
    title: 'Время в пути',
    key: 'total_travel_minutes',
    width: 50,
    sortable: false,
    align: 'center',
  },
]

const stopHeaders = [
  { title: '#', key: 'index', width: 60, sortable: false, align: 'center' },
  { title: 'Заявка', key: 'task_id', width: 160, sortable: false, align: 'center' },
  { title: 'Прибытие', key: 'arrival_time', width: 140, sortable: false, align: 'center' },
  { title: 'Начало', key: 'service_start_time', width: 140, sortable: false, align: 'center' },
  { title: 'Окончание', key: 'service_end_time', width: 140, sortable: false, align: 'center' },
  {
    title: 'В пути от пред.',
    key: 'travel_time_from_previous',
    width: 160,
    sortable: false,
    align: 'center',
  },
  {
    title: 'Расстояние от пред.',
    key: 'distance_from_previous_km',
    width: 180,
    sortable: false,
    align: 'center',
  },
  { title: 'Координаты', key: 'coordinates', width: 100, sortable: false, align: 'center' },
  { title: 'Действия', key: 'actions', width: 100, sortable: false, align: 'center' },
]

const formatKm = (v: number) => `${v.toFixed(2)} км`
const formatMin = (v: number) => `${v.toFixed(0)} мин`

const explanationDialogOpened = ref<boolean>(false)
const reassignmentDialogOpened = ref<boolean>(false)
const selectedStop = ref<RouteStop | null>(null)
const selectedRoute = ref<EngineerRoute | null>(null)

const openExplanationDialog = (stop: RouteStop, route: EngineerRoute) => {
  selectedStop.value = stop
  selectedRoute.value = route
  explanationDialogOpened.value = true
}

const closeExplanationDialog = () => {
  explanationDialogOpened.value = false
  selectedStop.value = null
  selectedRoute.value = null
}

const openReassignmentDialog = (stop: RouteStop, route: EngineerRoute) => {
  selectedStop.value = stop
  selectedRoute.value = route
  reassignmentDialogOpened.value = true
}

const closeReassignmentDialog = () => {
  reassignmentDialogOpened.value = false
  selectedStop.value = null
  selectedRoute.value = null
}
</script>

<template>
  <basic-card :loading="props.loading" title="Маршруты">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <v-data-table-virtual
      v-if="!props.loading"
      v-model="selected"
      class="routes-table"
      :items="routes.filter((item) => item.stops.length)"
      item-value="engineer_id"
      show-expand
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
          <td :colspan="columns.length" class="pa-0" style="background: lightgray !important">
            <basic-card title="Остановки маршрута" class="ma-3">
              <v-data-table-virtual
                class="stops-table"
                :headers="stopHeaders"
                :items="item.stops"
                density="compact"
                item-value="task_id"
                style="min-width: 1000px !important"
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
                <template #item.actions="props">
                  <v-row no-gutters class="text-no-wrap justify-center">
                    <icon-button
                      icon="info"
                      color="blue"
                      tooltip-text="Причины назначения"
                      @click="openExplanationDialog(props.item, item)"
                    />
                    <icon-button
                      icon="transfer_within_a_station"
                      color="warning"
                      tooltip-text="Переназначить исполнителя"
                      @click="openReassignmentDialog(props.item, item)"
                    />
                  </v-row>
                </template>
              </v-data-table-virtual>
            </basic-card>
          </td>
        </tr>
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
      :task-id="selectedStop ? selectedStop.task_id : null"
      @close="closeReassignmentDialog"
    />
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
