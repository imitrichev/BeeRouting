<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import type { Engineer } from '@/types/entities.ts'
import { computed } from 'vue'
import { getEngineerColor } from '@/utils/map.ts'
import { getSkillTranslation, getVehicleTypeTranslation } from '@/utils/translations.ts'
import { useDistrictDataStore } from '@/stores/districtData.ts'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()
const engineers = computed(() => districtDataStore.getDistrictEngineers)

const getSubtitle = (item: Engineer): string => {
  return `${getVehicleTypeTranslation(item.vehicle_type)} • ${item.available_from} - ${item.available_until}`
}
</script>

<template>
  <basic-card title="Инженеры" :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <v-list v-if="!props.loading" class="overflow-list" density="compact">
      <v-list-group v-for="item in engineers" :key="item.id">
        <template #activator="{ props: activatorProps }">
          <v-list-item v-bind="activatorProps" :title="item.name" :subtitle="getSubtitle(item)">
            <template #prepend>
              <v-avatar :color="getEngineerColor(item.id)"></v-avatar>
            </template>
          </v-list-item>
        </template>

        <v-list-item>
          <v-list-item-title class="text-subtitle-2">Квалификации</v-list-item-title>
          <div class="d-flex flex-wrap ga-1 mt-1">
            <v-chip
              v-for="skill in item.qualifications"
              :key="skill"
              size="small"
              color="primary"
              variant="tonal"
            >
              {{ getSkillTranslation(skill) }}
            </v-chip>
            <span v-if="!item.qualifications.length" class="text-medium-emphasis text-body-2">
              Нет данных
            </span>
          </div>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="text-subtitle-2">Тип транспорта</v-list-item-title>
          <div class="text-body-2 text-medium-emphasis mt-1">
            {{ getVehicleTypeTranslation(item.vehicle_type) }}
          </div>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="text-subtitle-2">Доступность</v-list-item-title>
          <div class="text-body-2 text-medium-emphasis mt-1">
            {{ item.available_from }} — {{ item.available_until }}
          </div>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="text-subtitle-2">Стартовая локация</v-list-item-title>
          <div class="text-body-2 text-medium-emphasis mt-1">
            ID: {{ item.start_location_id }}
            <template v-if="item.start_latitude !== null && item.start_longitude !== null">
              <br />
              Координаты: {{ item.start_latitude }}, {{ item.start_longitude }}
            </template>
          </div>
        </v-list-item>
      </v-list-group>
    </v-list>
  </basic-card>
</template>

<style scoped lang="scss"></style>
