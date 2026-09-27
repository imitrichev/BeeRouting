<script setup lang="ts">
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed, ref } from 'vue'
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import type { ReplanEventType, ReplanRequestData } from '@/types/entities.ts'
import { VEHICLE_TYPE_MAP } from '@/utils/consts.ts'
import { isValidTime, timeToMinutes } from '@/utils/time.ts'

interface IFormData {
  type: ReplanEventType

  consider_equipment: boolean

  engineer_id: string | null
  task_id: string | null

  emergency_task: {
    id: string
    latitude: number | null
    longitude: number | null
    work_type: string
    window_start: string
    window_end: string
    required_vehicle_type: string | null
    required_router_count: number
  }
}

const emit = defineEmits<{
  close: []
}>()

interface IProps {
  opened: boolean
}

const props = defineProps<IProps>()

const store = useDistrictDataStore()
const loading = computed(() => store.loadingReplan)

const defaultFormData: IFormData = {
  type: 'ENGINEER_UNAVAILABLE',
  consider_equipment: true,

  engineer_id: null,
  task_id: null,

  emergency_task: {
    id: '',
    latitude: null,
    longitude: null,
    work_type: '',
    window_start: '',
    window_end: '',
    required_vehicle_type: null,
    required_router_count: 1,
  },
}

const formData = ref<IFormData>({ ...defaultFormData })

const eventTypeSelectorItems = [
  {
    title: 'Инженер недоступен',
    value: 'ENGINEER_UNAVAILABLE',
  },
  {
    title: 'Заявка отменена',
    value: 'TASK_CANCELLED',
  },
  {
    title: 'Аварийная заявка',
    value: 'EMERGENCY_TASK',
  },
]

const vehicleTypeSelectorItems = computed(() =>
  Object.entries(VEHICLE_TYPE_MAP).map(([value, title]) => ({ value, title })),
)

const errors = ref<Record<string, string | null>>({
  engineer_id: null,
  task_id: null,
  emergency_task_id: null,
  emergency_task_latitude: null,
  emergency_task_longitude: null,
  emergency_task_window_start: null,
  emergency_task_window_end: null,
  emergency_task_required_router_count: null,
})

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

    if (t.latitude === null || t.latitude === undefined)
      errors.value.emergency_task_latitude = 'Укажите широту'
    else if (t.latitude < -90 || t.latitude > 90)
      errors.value.emergency_task_latitude = 'Широта должна быть в диапазоне от -90 до 90'

    if (t.longitude === null || t.longitude === undefined)
      errors.value.emergency_task_longitude = 'Укажите долготу'
    else if (t.longitude < -180 || t.longitude > 180)
      errors.value.emergency_task_longitude = 'Долгота должна быть в диапазоне от -180 до 180'

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

    if (
      isValidTime(t.window_start) &&
      isValidTime(t.window_end) &&
      timeToMinutes(t.window_start) >= timeToMinutes(t.window_end)
    ) {
      errors.value.emergency_task_window_end = 'Конец окна должен быть позже начала'
    }

    if (
      t.required_router_count === null ||
      t.required_router_count === undefined ||
      t.required_router_count <= 0
    ) {
      errors.value.emergency_task_required_router_count = 'Укажите количество роутеров больше 0'
    }
  }

  return !Object.values(errors.value).some((e) => e !== null)
}

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

const replan = async () => {
  if (!validateFormData()) return
  await store.loadReplan(prepareRequestData())
  emit('close')
}
</script>

<template>
  <v-dialog :model-value="props.opened" max-width="600">
    <basic-card title="Перепланирование заявок" :show-bottom="true">
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
        <template v-if="formData.type === 'ENGINEER_UNAVAILABLE'">
          <v-select
            v-model="formData.engineer_id"
            :items="store.getDistrictEngineersSelector"
            variant="outlined"
            label="Инженер"
            class="w-100 mt-3"
            :readonly="loading"
            :clearable="false"
            :error="!!errors.engineer_id"
            :error-messages="errors.engineer_id ?? ''"
          />
        </template>
        <template v-if="formData.type === 'TASK_CANCELLED'">
          <v-select
            v-model="formData.task_id"
            :items="store.getDistrictTasks"
            item-value="id"
            item-title="id"
            variant="outlined"
            label="Заявка"
            class="w-100 mt-3"
            :readonly="loading"
            :clearable="false"
            :error="!!errors.task_id"
            :error-messages="errors.task_id ?? ''"
          />
        </template>
        <template v-if="formData.type === 'EMERGENCY_TASK'">
          <v-alert type="info" variant="tonal" class="w-100 my-3">
            Тип "Аварийные работы" и приоритет "срочный" устанавливаются автоматически. Длительность
            берётся из норматива аварии.
          </v-alert>

          <v-text-field
            v-model="formData.emergency_task.id"
            variant="outlined"
            label="ID заявки"
            class="w-100 mt-3"
            :readonly="loading"
            :error="!!errors.emergency_task_id"
            :error-messages="errors.emergency_task_id ?? ''"
          />

          <v-row no-gutters class="w-100 mt-1">
            <v-col cols="6" class="pr-2">
              <v-text-field
                v-model.number="formData.emergency_task.latitude"
                variant="outlined"
                label="Широта"
                type="number"
                :readonly="loading"
                :error="!!errors.emergency_task_latitude"
                :error-messages="errors.emergency_task_latitude ?? ''"
              />
            </v-col>
            <v-col cols="6" class="pl-2">
              <v-text-field
                v-model.number="formData.emergency_task.longitude"
                variant="outlined"
                label="Долгота"
                type="number"
                :readonly="loading"
                :error="!!errors.emergency_task_longitude"
                :error-messages="errors.emergency_task_longitude ?? ''"
              />
            </v-col>
          </v-row>

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
.overflow-list {
  max-height: 80vh !important;
  min-height: unset !important;
}
</style>
