<script setup lang="ts">
/**
 * Диалог перепланирования заявок по событию.
 *
 * Поддерживает три типа событий:
 * - `ENGINEER_UNAVAILABLE` — инженер стал недоступен (выбор инженера);
 * - `TASK_CANCELLED` — отмена заявки (выбор заявки);
 * - `EMERGENCY_TASK` — аварийная заявка (форма с картой для выбора точки,
 *   ID, временным окном, транспортом и числом роутеров).
 *
 * После подтверждения отправляет запрос через `districtDataStore.loadReplan`
 * и эмитит `close` с `applied = true`.
 */

import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import type { ReplanEventType, ReplanRequestData } from '@/types/entities.ts'
import { VEHICLE_TYPE_MAP } from '@/utils/consts.ts'
import { isValidTime, timeToMinutes } from '@/utils/time.ts'
import { Map, Marker, NavigationControl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

/**
 * Данные формы перепланирования.
 */
interface IFormData {
  /** Тип события. */
  type: ReplanEventType
  /** Учитывать требуемое оборудование. */
  consider_equipment: boolean
  /** Идентификатор инженера (для `ENGINEER_UNAVAILABLE`). */
  engineer_id: string | null
  /** Идентификатор задачи (для `TASK_CANCELLED`). */
  task_id: string | null
  /** Данные аварийной задачи (для `EMERGENCY_TASK`). */
  emergency_task: {
    /** Идентификатор задачи. */
    id: string
    /** Широта точки. */
    latitude: number | null
    /** Долгота точки. */
    longitude: number | null
    /** Тип работ. */
    work_type: string
    /** Начало окна в формате `HH:mm`. */
    window_start: string
    /** Конец окна в формате `HH:mm`. */
    window_end: string
    /** Требуемый тип транспорта (или `null`). */
    required_vehicle_type: string | null
    /** Требуемое число роутеров. */
    required_router_count: number
  }
}

/**
 * События компонента.
 */
const emit = defineEmits<{
  /** Закрытие диалога; `applied` — применено ли перепланирование. */
  close: [applied: boolean]
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

/** Флаг загрузки запроса перепланирования. */
const loading = computed(() => store.loadingReplan)

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
  type: 'ENGINEER_UNAVAILABLE',
  consider_equipment: true,

  engineer_id: null,
  task_id: null,

  emergency_task: {
    id: '',
    latitude: DEFAULT_LATITUDE,
    longitude: DEFAULT_LONGITUDE,
    work_type: '',
    window_start: '10:00',
    window_end: '12:00',
    required_vehicle_type: null,
    required_router_count: 0,
  },
})

/** Данные формы. */
const formData = ref<IFormData>(createDefaultFormData())

/** Элементы селектора доступных типов событий. */
const eventTypeSelectorItems = computed(() => {
  const items: { title: string; value: ReplanEventType }[] = []
  if (activeEngineersSelectorItems.value.length > 0) {
    items.push({ title: 'Инженер недоступен', value: 'ENGINEER_UNAVAILABLE' })
  }
  if (cancellableTaskSelectorItems.value.length > 0) {
    items.push({ title: 'Заявка отменена', value: 'TASK_CANCELLED' })
  }
  items.push({ title: 'Аварийная заявка', value: 'EMERGENCY_TASK' })
  return items
})

/** Элементы селектора отменяемых задач (все, кроме отменённых). */
const cancellableTaskSelectorItems = computed(() =>
  store.getDistrictTasks
    .filter((t) => t.status !== 'CANCELLED')
    .map((t) => ({ title: t.id, value: t.id })),
)

/** Элементы селектора типов транспорта. */
const vehicleTypeSelectorItems = computed(() =>
  Object.entries(VEHICLE_TYPE_MAP).map(([value, title]) => ({ value, title })),
)

/** Элементы селектора активных инженеров. */
const activeEngineersSelectorItems = computed(() =>
  store.getDistrictEngineers
    .filter((e) => e.is_active)
    .map((e) => ({ title: e.name, value: e.id })),
)

/** Ошибки валидации по полям формы. */
const errors = ref<Record<string, string | null>>({
  engineer_id: null,
  task_id: null,
  emergency_task_id: null,
  emergency_task_window_start: null,
  emergency_task_window_end: null,
  emergency_task_required_router_count: null,
})

/** Сбрасывает форму, ошибки и маркер карты в значения по умолчанию. */
const resetForm = () => {
  formData.value = createDefaultFormData()
  Object.keys(errors.value).forEach((k) => (errors.value[k] = null))
  resetMarkerToDefault()
}

// --- Карта аварийной задачи -------------------------------------------------

/** DOM-контейнер карты. */
const emergencyMapContainer = ref<HTMLElement | null>(null)
/** Инстанс карты. */
let emergencyMap: Map | null = null
/** Маркер выбранной точки. */
let emergencyMarker: Marker | null = null

/** Возвращает маркер и координаты формы в значения по умолчанию. */
const resetMarkerToDefault = () => {
  if (!emergencyMap) return
  setMarker(DEFAULT_LONGITUDE, DEFAULT_LATITUDE)
  formData.value.emergency_task.latitude = DEFAULT_LATITUDE
  formData.value.emergency_task.longitude = DEFAULT_LONGITUDE
}

/**
 * Устанавливает маркер в указанных координатах.
 *
 * @param lng Долгота.
 * @param lat Широта.
 */
const setMarker = (lng: number, lat: number) => {
  if (!emergencyMap) return
  if (emergencyMarker) {
    emergencyMarker.remove()
    emergencyMarker = null
  }
  emergencyMarker = new Marker({ color: '#e53935' }).setLngLat([lng, lat]).addTo(emergencyMap)
}

/** Инициализирует карту аварийной задачи и навешивает обработчики. */
const initMap = async () => {
  if (emergencyMap) return
  if (!emergencyMapContainer.value) return

  emergencyMap = new Map({
    container: emergencyMapContainer.value,
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

  emergencyMap.addControl(
    new NavigationControl({
      showZoom: true,
      showCompass: false,
      visualizePitch: true,
    }),
    'top-right',
  )

  emergencyMap.on('load', () => {
    emergencyMap?.resize()
  })

  // Клик по карте — выбор координат аварийной задачи
  emergencyMap.on('click', (e) => {
    const lng = e.lngLat.lng
    const lat = e.lngLat.lat

    setMarker(lng, lat)
    formData.value.emergency_task.latitude = lat
    formData.value.emergency_task.longitude = lng
  })

  setMarker(DEFAULT_LONGITUDE, DEFAULT_LATITUDE)

  await nextTick()
  emergencyMap.resize()
}

/** Уничтожает маркер и карту. */
const destroyMap = () => {
  if (emergencyMarker) {
    emergencyMarker.remove()
    emergencyMarker = null
  }
  if (emergencyMap) {
    emergencyMap.remove()
    emergencyMap = null
  }
}

// --- Жизненный цикл ---------------------------------------------------------

/**
 * Реакция на открытие/закрытие диалога:
 * при открытии — сброс формы и валидация доступности выбранного типа события;
 * при закрытии — уничтожение карты.
 */
watch(
  () => props.opened,
  (opened) => {
    if (opened) {
      resetForm()

      const availableTypes = eventTypeSelectorItems.value.map((i) => i.value)
      if (!availableTypes.includes(formData.value.type)) {
        formData.value.type = 'EMERGENCY_TASK'
      }
    } else {
      destroyMap()
    }
  },
)

/**
 * Реакция на смену типа события:
 * для `EMERGENCY_TASK` — инициализация карты, иначе — уничтожение.
 */
watch(
  () => formData.value.type,
  async (type) => {
    if (type === 'EMERGENCY_TASK' && props.opened) {
      await nextTick()
      await initMap()
    } else {
      destroyMap()
    }
  },
)

/** Уничтожает карту перед размонтированием компонента. */
onBeforeUnmount(() => {
  destroyMap()
})

// --- Валидация и отправка ---------------------------------------------------

/**
 * Валидирует форму в зависимости от выбранного типа события.
 *
 * @returns `true`, если форма валидна.
 */
const validateFormData = (): boolean => {
  Object.keys(errors.value).forEach((k) => (errors.value[k] = null))

  if (formData.value.type === 'ENGINEER_UNAVAILABLE') {
    if (!formData.value.engineer_id) {
      errors.value.engineer_id = 'Выберите инженера'
    }
  }

  if (formData.value.type === 'TASK_CANCELLED') {
    if (!formData.value.task_id) {
      errors.value.task_id = 'Выберите заявку'
    }
  }

  if (formData.value.type === 'EMERGENCY_TASK') {
    const t = formData.value.emergency_task

    if (!t.id) errors.value.emergency_task_id = 'Укажите ID заявки'

    if (!t.window_start) {
      errors.value.emergency_task_window_start = 'Укажите начало окна'
    } else if (!isValidTime(t.window_start)) {
      errors.value.emergency_task_window_start = 'Формат времени: ЧЧ:ММ'
    }

    if (!t.window_end) {
      errors.value.emergency_task_window_end = 'Укажите конец окна'
    } else if (!isValidTime(t.window_end)) {
      errors.value.emergency_task_window_end = 'Формат времени: ЧЧ:ММ'
    }

    // Конец окна должен быть строго позже начала
    if (
      isValidTime(t.window_start) &&
      isValidTime(t.window_end) &&
      timeToMinutes(t.window_start) >= timeToMinutes(t.window_end)
    ) {
      errors.value.emergency_task_window_end = 'Конец окна должен быть позже начала'
    }

    if (t.required_router_count && t.required_router_count < 0) {
      errors.value.emergency_task_required_router_count = 'Укажите количество роутеров больше 0'
    }
  }

  return !Object.values(errors.value).some((e) => e !== null)
}

/**
 * Формирует тело запроса для перепланирования.
 * Предполагается, что форма уже прошла валидацию.
 *
 * @returns Данные запроса.
 */
const prepareRequestData = (): ReplanRequestData => {
  if (formData.value.type === 'ENGINEER_UNAVAILABLE') {
    return {
      event_type: 'ENGINEER_UNAVAILABLE',
      consider_equipment: store.currentConsiderEquipment,
      engineer_id: formData.value.engineer_id!,
    }
  }

  if (formData.value.type === 'TASK_CANCELLED') {
    return {
      event_type: 'TASK_CANCELLED',
      consider_equipment: store.currentConsiderEquipment,
      task_id: formData.value.task_id!,
    }
  }

  const t = formData.value.emergency_task
  return {
    event_type: 'EMERGENCY_TASK',
    consider_equipment: store.currentConsiderEquipment,
    task: {
      id: t.id,
      latitude: t.latitude!,
      longitude: t.longitude!,
      work_type: 'EMERGENCY',
      window_start: t.window_start,
      window_end: t.window_end,
      required_vehicle_type: t.required_vehicle_type ?? null,
      required_router_count: t.required_router_count ?? 0,
    },
  }
}

/**
 * Валидирует форму, отправляет запрос на перепланирование и закрывает диалог.
 * При успехе эмитит `close` с `applied = true`.
 */
const replan = async () => {
  if (!validateFormData()) return
  await store.loadReplan(prepareRequestData())
  emit('close', true)
}
</script>

<template>
  <v-dialog
    persistent
    :model-value="props.opened"
    max-width="600"
    @after-enter="
      () => {
        if (formData.type === 'EMERGENCY_TASK') initMap()
      }
    "
  >
    <basic-card title="Перепланирование заявок" :show-bottom="true">
      <template #toolbarAppend>
        <icon-button
          icon="close"
          class="ml-3"
          :loading="loading"
          @click="emit('close', false)"
          tooltip-text="Закрыть"
        />
      </template>

      <v-row no-gutters class="overflow-list default-scrollbar px-4 py-4">
        <!-- Тип события -->
        <v-select
          v-model="formData.type"
          :items="eventTypeSelectorItems"
          variant="outlined"
          label="Событие"
          class="w-100 mb-3"
          hide-details
          :readonly="loading"
          :clearable="false"
        />

        <!-- Инженер недоступен -->
        <template v-if="formData.type === 'ENGINEER_UNAVAILABLE'">
          <v-select
            v-model="formData.engineer_id"
            :items="activeEngineersSelectorItems"
            variant="outlined"
            label="Инженер"
            class="w-100 mt-3"
            :readonly="loading"
            :clearable="false"
            :error="!!errors.engineer_id"
            :error-messages="errors.engineer_id ?? ''"
          />
        </template>

        <!-- Заявка отменена -->
        <template v-if="formData.type === 'TASK_CANCELLED'">
          <v-select
            v-model="formData.task_id"
            :items="cancellableTaskSelectorItems"
            item-value="value"
            item-title="title"
            variant="outlined"
            label="Заявка"
            class="w-100 mt-3"
            :readonly="loading"
            :clearable="false"
            :error="!!errors.task_id"
            :error-messages="errors.task_id ?? ''"
          />
        </template>

        <!-- Аварийная заявка -->
        <template v-if="formData.type === 'EMERGENCY_TASK'">
          <v-alert type="info" variant="flat" class="w-100 my-3">
            Тип "Аварийные работы" и приоритет "срочный" устанавливаются автоматически. Длительность
            берётся из норматива аварии.
          </v-alert>

          <v-row no-gutters class="w-100">
            <v-col cols="12">
              <v-card-title class="px-2 text-body-large">Укажите место:</v-card-title>
            </v-col>
            <v-col cols="12">
              <div class="w-100 mb-3 emergency-map-wrapper">
                <div ref="emergencyMapContainer" class="emergency-map" />
              </div>
            </v-col>
          </v-row>

          <v-text-field
            v-model="formData.emergency_task.id"
            variant="outlined"
            label="ID заявки"
            class="w-100 mt-3"
            :readonly="loading"
            :error="!!errors.emergency_task_id"
            :error-messages="errors.emergency_task_id ?? ''"
          />

          <!-- Временное окно аварийной задачи -->
          <v-row no-gutters class="w-100 mt-1">
            <v-col cols="6" class="pr-2">
              <v-text-field
                v-model="formData.emergency_task.window_start"
                variant="outlined"
                label="Начало окна"
                placeholder="ЧЧ:ММ"
                :readonly="loading"
                :error="!!errors.emergency_task_window_start"
                :error-messages="errors.emergency_task_window_start ?? ''"
              />
            </v-col>
            <v-col cols="6" class="pl-2">
              <v-text-field
                v-model="formData.emergency_task.window_end"
                variant="outlined"
                label="Конец окна"
                placeholder="ЧЧ:ММ"
                :readonly="loading"
                :error="!!errors.emergency_task_window_end"
                :error-messages="errors.emergency_task_window_end ?? ''"
              />
            </v-col>
          </v-row>

          <v-select
            v-model="formData.emergency_task.required_vehicle_type"
            :items="vehicleTypeSelectorItems"
            variant="outlined"
            label="Необходимый транспорт"
            class="w-100 mt-3"
            clearable
            :readonly="loading"
          />

          <v-text-field
            v-model.number="formData.emergency_task.required_router_count"
            variant="outlined"
            label="Количество роутеров"
            type="number"
            class="w-100 mt-3"
            :readonly="loading"
            :error="!!errors.emergency_task_required_router_count"
            :error-messages="errors.emergency_task_required_router_count ?? ''"
          />
        </template>
      </v-row>

      <template #bottom>
        <v-row no-gutters class="justify-end pb-2">
          <v-btn
            :loading="loading"
            color="primary"
            variant="flat"
            class="text-none"
            @click="replan"
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

/** Обёртка карты выбора точки аварийной задачи. */
.emergency-map-wrapper {
  width: 100%;
  height: 300px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.emergency-map {
  width: 100%;
  height: 300px;
}
</style>
