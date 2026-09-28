<script setup lang="ts">
/**
 * Диалог создания задачи.
 *
 * Содержит форму с полями: ID, тип работ, временное окно (`HH:mm`),
 * требуемый транспорт и количество роутеров. Также встроена карта MapLibre,
 * на которой пользователь выбирает точку задачи кликом; координаты
 * подставляются в форму.
 *
 * При открытии форма сбрасывается и карта инициализируется; при закрытии —
 * карта уничтожается.
 */

import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import type { TaskCreateRequestData } from '@/types/entities.ts'
import { VEHICLE_TYPE_MAP, WORK_TYPE_MAP } from '@/utils/consts.ts'
import { isValidTime, timeToMinutes } from '@/utils/time.ts'
import { Map, Marker, NavigationControl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

/**
 * Данные формы создания задачи.
 */
interface IFormData {
  /** Идентификатор задачи. */
  id: string
  /** Адрес (текстовое описание). */
  address: string
  /** Широта выбранной точки. */
  latitude: number | null
  /** Долгота выбранной точки. */
  longitude: number | null
  /** Код типа работ. */
  work_type: string | null
  /** Начало временного окна в формате `HH:mm`. */
  window_start: string
  /** Конец временного окна в формате `HH:mm`. */
  window_end: string
  /** Код требуемого типа транспорта (или `null`). */
  required_vehicle_type: string | null
  /** Требуемое количество роутеров. */
  required_router_count: number
}

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

const store = useDistrictDataStore()

/** Флаг загрузки запроса создания задачи. */
const loading = computed(() => store.loadingCreateTask)

/** Координаты и зум карты по умолчанию (совпадают с AppMap). */
const DEFAULT_LATITUDE = 55.7528
const DEFAULT_LONGITUDE = 37.6178
const DEFAULT_ZOOM = 10

/**
 * Возвращает форму с дефолтными значениями.
 *
 * @returns Новая форма.
 */
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

/** Данные формы. */
const formData = ref<IFormData>(createDefaultFormData())

/** Элементы селектора типов работ. */
const workTypeSelectorItems = computed(() =>
  Object.entries(WORK_TYPE_MAP).map(([value, title]) => ({ value, title })),
)

/** Элементы селектора типов транспорта. */
const vehicleTypeSelectorItems = computed(() =>
  Object.entries(VEHICLE_TYPE_MAP).map(([value, title]) => ({ value, title })),
)

/** Ошибки валидации по полям формы. */
const errors = ref<Record<string, string | null>>({
  id: null,
  work_type: null,
  window_start: null,
  window_end: null,
  required_router_count: null,
})

/** Сбрасывает форму, ошибки и маркер на карте в значения по умолчанию. */
const resetForm = () => {
  formData.value = createDefaultFormData()
  Object.keys(errors.value).forEach((k) => (errors.value[k] = null))
  resetMarkerToDefault()
}

// --- Карта ------------------------------------------------------------------

/** DOM-контейнер карты. */
const createMapContainer = ref<HTMLElement | null>(null)
/** Инстанс карты. */
let createMap: Map | null = null
/** Маркер выбранной точки. */
let createMarker: Marker | null = null

/** Возвращает маркер и координаты формы в значения по умолчанию. */
const resetMarkerToDefault = () => {
  if (!createMap) return
  setMarker(DEFAULT_LONGITUDE, DEFAULT_LATITUDE)
  formData.value.latitude = DEFAULT_LATITUDE
  formData.value.longitude = DEFAULT_LONGITUDE
}

/**
 * Устанавливает маркер в указанных координатах.
 *
 * @param lng Долгота.
 * @param lat Широта.
 */
const setMarker = (lng: number, lat: number) => {
  if (!createMap) return
  if (createMarker) {
    createMarker.remove()
    createMarker = null
  }
  createMarker = new Marker({ color: '#1976d2' }).setLngLat([lng, lat]).addTo(createMap)
}

/** Инициализирует карту и навешивает обработчики (один раз). */
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

  // Клик по карте — выбор координат задачи
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

/** Уничтожает маркер и карту. */
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

// --- Жизненный цикл ---------------------------------------------------------

/**
 * Реакция на открытие/закрытие диалога:
 * при открытии — сброс формы; при закрытии — уничтожение карты.
 */
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

/** Уничтожает карту перед размонтированием компонента. */
onBeforeUnmount(() => {
  destroyMap()
})

// --- Валидация и создание ---------------------------------------------------

/**
 * Валидирует форму и заполняет `errors`.
 *
 * @returns `true`, если форма валидна.
 */
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

  // Конец окна должен быть строго позже начала
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

/**
 * Формирует тело запроса для создания задачи.
 * Предполагается, что форма уже прошла валидацию.
 *
 * @returns Данные запроса.
 */
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

/**
 * Валидирует форму, отправляет запрос на создание задачи и закрывает диалог.
 */
const createTask = async () => {
  if (!validateFormData()) return
  await store.loadCreateTask(prepareRequestData())
  emit('close')
}
</script>

<template>
  <v-dialog :model-value="props.opened" max-width="600" @after-enter="initMap" persistent>
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
        <!-- Карта выбора точки -->
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

        <!-- Временное окно: начало и конец -->
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
/**
 * Ограничивает высоту контента диалога 80% высоты вьюпорта
 * с вертикальной прокруткой при переполнении.
 */
.overflow-list {
  max-height: 80vh !important;
  min-height: unset !important;
}

/** Обёртка карты выбора точки задачи. */
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
