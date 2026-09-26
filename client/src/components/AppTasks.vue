<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import type { Task } from '@/types/entities.ts'
import {
  getPriorityTranslation,
  getSkillTranslation,
  getVehicleTypeTranslation,
} from '@/utils/translations.ts'
import { computed } from 'vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()
const tasks = computed(() => districtDataStore.getDistrictTasks)

const getSubtitle = (item: Task): string => {
  const skill = getSkillTranslation(item.required_skill)
  const start = item.window_start
  const end = item.window_end
  return `${skill} • ${start}-${end} • ${item.duration_minutes} мин.`
}

const getPriorityColor = (priority: string): string => {
  return priority === 'URGENT' ? 'error' : 'default'
}
</script>

<template>
  <basic-card title="Заявки" :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>

    <v-list v-if="!props.loading" class="overflow-list" density="compact">
      <v-list-group v-for="item in tasks" :key="item.id">
        <template #activator="{ props: activatorProps }">
          <v-list-item v-bind="activatorProps" :title="item.id" :subtitle="getSubtitle(item)" />
        </template>

        <v-list-item>
          <v-list-item-title class="text-subtitle-2">Квалификация</v-list-item-title>
          <div class="text-body-2 text-medium-emphasis mt-1">
            {{ getSkillTranslation(item.required_skill) }}
          </div>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="text-subtitle-2">Окно выполнения</v-list-item-title>
          <div class="text-body-2 text-medium-emphasis mt-1">
            {{ item.window_start }} — {{ item.window_end }} ({{ item.duration_minutes }} мин.)
          </div>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="text-subtitle-2">Приоритет</v-list-item-title>
          <div class="mt-1">
            <v-chip size="small" variant="tonal" :color="getPriorityColor(item.priority)">
              {{ getPriorityTranslation(item.priority) }}
            </v-chip>
          </div>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="text-subtitle-2">Требуемый транспорт</v-list-item-title>
          <div class="text-body-2 text-medium-emphasis mt-1">
            {{ getVehicleTypeTranslation(item.required_vehicle_type) }}
          </div>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="text-subtitle-2">Локация</v-list-item-title>
          <div class="text-body-2 text-medium-emphasis mt-1">
            ID: {{ item.location_id }}
            <template v-if="item.latitude !== null && item.longitude !== null">
              <br />
              Координаты: {{ item.latitude }}, {{ item.longitude }}
            </template>
          </div>
        </v-list-item>
      </v-list-group>
    </v-list>
  </basic-card>
</template>

<style scoped lang="scss">
.overflow-list :deep(.v-list-item) {
  overflow: visible;
  min-height: auto;
}
</style>
