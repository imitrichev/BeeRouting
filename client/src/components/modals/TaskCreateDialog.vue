<script setup lang="ts">
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import type { TaskCreateRequestData } from '@/types/entities.ts'
import { VEHICLE_TYPE_MAP, WORK_TYPE_MAP } from '@/utils/consts.ts'
import { isValidTime, timeToMinutes } from '@/utils/time.ts'
import { Map, Marker, NavigationControl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

interface IFormData {
  id: string
  address: string
  latitude: number | null
  longitude: number | null
  work_type: string | null
  window_start: string
  window_end: string
  required_vehicle_type: string | null
  required_router_count: number
}

const emit = defineEmits<{
  close: []
}>()

interface IProps {
  opened: boolean
}

const props = defineProps<IProps>()

const store = useDistrictDataStore()
const loading = computed(() => store.loadingCreateTask)

/** Дефолтные координаты — те же, что в AppMap */
const DEFAULT_LATITUDE = 55.7528
const DEFAULT_LONGITUDE = 37.6178
const DEFAULT_ZOOM = 10

const createDefaultFormData = (): IFormData => ({
  id: '',
  address: '',
  latitude: DEFAULT_LATITUDE,
  longitude: DEFAULT_LONGITUDE,
  work_type: 'CONNECTION',
  window_start: '12:00',
  window_end: '14:00',
  required_vehicle_type: null,
  required_router_count: 0,
})

const formData = ref<IFormData>(createDefaultFormData())

const workTypeSelectorItems = computed(() =>
  Object.entries(WORK_TYPE_MAP).map(([value, title]) => ({ value, title })),
)
const vehicleTypeSelectorItems = computed(() =>
  Object.entries(VEHICLE_TYPE_MAP).map(([value, title]) => ({ value, title })),
)

const errors = ref<Record<string, string | null>>({
  id: null,
  work_type: null,
  window_start: null,
  window_end: null,
  required_router_count: null,
})

const resetForm = () => {
  formData.value = createDefaultFormData()
  Object.keys(errors.value).forEach((k) => (errors.value[k] = null))
  resetMarkerToDefault()
}

/* ----------------------------- Карта ----------------------------- */

const createMapContainer = ref<HTMLElement | null>(null)
let createMap: Map | null = null
let createMarker: Marker | null = null

const resetMarkerToDefault = () => {
  if (!createMap) return
  setMarker(DEFAULT_LONGITUDE, DEFAULT_LATITUDE)
  formData.value.latitude = DEFAULT_LATITUDE
  formData.value.longitude = DEFAULT_LONGITUDE
}

const setMarker = (lng: number, lat: number) => {
  if (!createMap) return
  if (createMarker) {
    createMarker.remove()
    createMarker = null
  }
  createMarker = new Marker({ color: '#1976d2' }).setLngLat([lng, lat]).addTo(createMap)
}

const initMap = async () => {
  if (createMap) return
  if (!createMapContainer.value) return

  createMap = new Map({
    container: createMapContainer.value,
    style: {
      version: 8,
      sources: {
        openstreetmap: {
          type: 'raster',
          tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          attribution: '© OpenStreetMap contributors',
        },
      },
      layers: [
        {
          id: 'openstreetmap',
          type: 'raster',
          source: 'openstreetmap',
        },
      ],
    },
    center: [DEFAULT_LONGITUDE, DEFAULT_LATITUDE],
    zoom: DEFAULT_ZOOM,
  })

  createMap.addControl(
    new NavigationControl({
      showZoom: true,
      showCompass: false,
      visualizePitch: true,
    }),
    'top-right',
  )

  createMap.on('load', () => {
    createMap?.resize()
  })

  createMap.on('click', (e) => {
    const lng = e.lngLat.lng
    const lat = e.lngLat.lat

    setMarker(lng, lat)
    formData.value.latitude = lat
    formData.value.longitude = lng
  })

  setMarker(DEFAULT_LONGITUDE, DEFAULT_LATITUDE)

  await nextTick()
  createMap.resize()
}

const destroyMap = () => {
  if (createMarker) {
    createMarker.remove()
    createMarker = null
  }
  if (createMap) {
    createMap.remove()
    createMap = null
  }
}

/* --------------------------- Жизненный цикл --------------------------- */

watch(
  () => props.opened,
  (opened) => {
    if (opened) {
      resetForm()
    } else {
      destroyMap()
    }
  },
)

onBeforeUnmount(() => {
  destroyMap()
})

/* ----------------------------- Валидация ----------------------------- */

const validateFormData = (): boolean => {
  Object.keys(errors.value).forEach((k) => (errors.value[k] = null))

  const f = formData.value

  if (!f.id) errors.value.id = 'Укажите ID заявки'
  if (!f.work_type) errors.value.work_type = 'Выберите тип работ'

  if (!f.window_start) {
    errors.value.window_start = 'Укажите начало окна'
  } else if (!isValidTime(f.window_start)) {
    errors.value.window_start = 'Формат времени: ЧЧ:ММ'
  }

  if (!f.window_end) {
    errors.value.window_end = 'Укажите конец окна'
  } else if (!isValidTime(f.window_end)) {
    errors.value.window_end = 'Формат времени: ЧЧ:ММ'
  }

  if (
    isValidTime(f.window_start) &&
    isValidTime(f.window_end) &&
    timeToMinutes(f.window_start) >= timeToMinutes(f.window_end)
  ) {
    errors.value.window_end = 'Конец окна должен быть позже начала'
  }

  if (
    f.required_router_count === null ||
    f.required_router_count === undefined ||
    f.required_router_count < 0
  ) {
    errors.value.required_router_count = 'Количество роутеров не может быть отрицательным'
  }

  return !Object.values(errors.value).some((e) => e !== null)
}

const prepareRequestData = (): TaskCreateRequestData => {
  const f = formData.value
  return {
    id: f.id,
    address: f.address,
    latitude: f.latitude!,
    longitude: f.longitude!,
    work_type: f.work_type as TaskCreateRequestData['work_type'],
    window_start: f.window_start,
    window_end: f.window_end,
    required_vehicle_type: f.required_vehicle_type ?? null,
    required_router_count: f.required_router_count ?? 0,
  }
}

const createTask = async () => {
  if (!validateFormData()) return
  await store.loadCreateTask(prepareRequestData())
  emit('close')
}
</script>

<template>
  <v-dialog :model-value="props.opened" max-width="600" @after-enter="initMap">
    <basic-card title="Создание заявки" :show-bottom="true">
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
        <v-row no-gutters class="w-100">
          <v-col cols="12">
            <v-card-title class="px-2 pt-0 text-body-large">Укажите место:</v-card-title>
          </v-col>
          <v-col cols="12">
            <div class="w-100 mb-5 task-create-map-wrapper">
              <div ref="createMapContainer" class="task-create-map" />
            </div>
          </v-col>
        </v-row>
        <v-text-field
          v-model="formData.id"
          variant="outlined"
          label="ID заявки"
          class="w-100 mb-3"
          :readonly="loading"
          :error="!!errors.id"
          :error-messages="errors.id ?? ''"
        />

        <v-select
          v-model="formData.work_type"
          :items="workTypeSelectorItems"
          variant="outlined"
          label="Тип работ"
          class="w-100 mb-3"
          :readonly="loading"
          :clearable="false"
          :error="!!errors.work_type"
          :error-messages="errors.work_type ?? ''"
        />

        <v-row no-gutters class="w-100">
          <v-col cols="6" class="pr-2">
            <v-text-field
              v-model="formData.window_start"
              variant="outlined"
              label="Начало окна"
              placeholder="ЧЧ:ММ"
              :readonly="loading"
              :error="!!errors.window_start"
              :error-messages="errors.window_start ?? ''"
            />
          </v-col>
          <v-col cols="6" class="pl-2">
            <v-text-field
              v-model="formData.window_end"
              variant="outlined"
              label="Конец окна"
              placeholder="ЧЧ:ММ"
              :readonly="loading"
              :error="!!errors.window_end"
              :error-messages="errors.window_end ?? ''"
            />
          </v-col>
        </v-row>

        <v-select
          v-model="formData.required_vehicle_type"
          :items="vehicleTypeSelectorItems"
          variant="outlined"
          label="Необходимый транспорт"
          class="w-100 mt-3"
          clearable
          :readonly="loading"
        />

        <v-text-field
          v-model.number="formData.required_router_count"
          variant="outlined"
          label="Количество роутеров"
          type="number"
          class="w-100 mt-3"
          :readonly="loading"
          :error="!!errors.required_router_count"
          :error-messages="errors.required_router_count ?? ''"
        />
      </v-row>
      <template #bottom>
        <v-row no-gutters class="justify-end pb-2">
          <v-btn
            :loading="loading"
            color="primary"
            variant="flat"
            class="text-none"
            @click="createTask"
          >
            Создать
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

.task-create-map-wrapper {
  width: 100%;
  height: 300px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.task-create-map {
  width: 100%;
  height: 300px;
}
</style>
