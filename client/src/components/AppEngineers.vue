<script setup lang="ts">
/**
 * Таблица инженеров района.
 *
 * Отображает список инженеров с колонками: имя (с цветовым маркером),
 * активность, квалификации, тип транспорта, доступное число роутеров,
 * рабочий день и стартовая локация.
 *
 * Цвет маркера имени совпадает с цветом маршрута инженера на карте
 * (`getEngineerColor`), что позволяет визуально связать таблицу и карту.
 */

import BasicCard from '@/templates/BasicCard.vue'
import type { Engineer } from '@/types/entities.ts'
import { computed } from 'vue'
import { getEngineerColor } from '@/utils/map.ts'
import { getSkillTranslation, getVehicleTypeTranslation } from '@/utils/translations.ts'
import { useDistrictDataStore } from '@/stores/districtData.ts'

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Флаг загрузки: переключает карточку в состояние скелетона. */
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()

/** Список инженеров района. */
const engineers = computed<Engineer[]>(() => districtDataStore.getDistrictEngineers)

/** Колонки таблицы инженеров. */
const engineerHeaders = [
  { title: 'Название', key: 'name', width: 200, sortable: true, align: 'start' },
  { title: 'Доступен', key: 'is_active', width: 100, sortable: true, align: 'center' },
  { title: 'Квалификации', key: 'qualifications', width: 260, sortable: false, align: 'center' },
  {
    title: 'Тип транспорта',
    key: 'vehicle_type',
    width: 160,
    sortable: false,
    align: 'center',
  },
  {
    title: 'Доступно роутеров',
    key: 'available_router_count',
    width: 160,
    sortable: true,
    align: 'center',
  },
  { title: 'Рабочий день', key: 'availability', width: 200, sortable: false, align: 'center' },
  {
    title: 'Стартовая локация',
    key: 'start_address',
    width: 240,
    sortable: false,
    align: 'center',
  },
] as const
</script>

<template>
  <basic-card title="Инженеры" :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>

    <v-data-table-virtual
      v-if="!props.loading"
      class="engineers-table"
      :headers="engineerHeaders"
      :items="engineers"
      item-value="id"
      density="comfortable"
      fixed-header
      height="400"
    >
      <!-- Имя с цветовым маркером -->
      <template #item.name="{ item }">
        <div class="d-flex align-center justify-start ga-2">
          <v-avatar size="20" :color="getEngineerColor(item.id, engineers)" />
          <span>{{ item.name }}</span>
        </div>
      </template>

      <!-- Активность: иконка-галочка/крестик -->
      <template #item.is_active="{ item }">
        <v-icon
          :color="item.is_active ? 'success' : 'error'"
          :icon="item.is_active ? 'check_circle' : 'cancel'"
          size="small"
        />
      </template>

      <!-- Квалификации: чипы или прочерк -->
      <template #item.qualifications="{ item }">
        <div class="d-flex flex-wrap justify-center ga-1 py-1">
          <v-chip
            v-for="skill in item.qualifications"
            :key="skill"
            size="x-small"
            color="primary"
            variant="tonal"
          >
            {{ getSkillTranslation(skill) }}
          </v-chip>
          <span v-if="!item.qualifications.length" class="text-medium-emphasis">-</span>
        </div>
      </template>

      <template #item.vehicle_type="{ item }">
        {{ getVehicleTypeTranslation(item.vehicle_type) }}
      </template>

      <template #item.available_router_count="{ item }">
        {{ item.available_router_count }}
      </template>

      <!-- Рабочий день: интервал, если инженер активен -->
      <template #item.availability="{ item }">
        <template v-if="item.is_active">
          {{ item.available_from }} - {{ item.available_until }}
        </template>
        <span v-else class="text-medium-emphasis">-</span>
      </template>

      <template #item.start_address="{ item }">
        {{ item.start_address || '-' }}
      </template>
    </v-data-table-virtual>
  </basic-card>
</template>

<style scoped lang="scss">
/**
 * Таблица инженеров: предотвращает переполнение по горизонтали
 * и включает горизонтальную прокрутку для широкого контента.
 */
.engineers-table :deep(.v-table__wrapper),
.engineers-table :deep(.v-table__wrapper > table) {
  min-width: 0;
}

:deep(.v-table__wrapper) {
  overflow-x: auto !important;
}
</style>
