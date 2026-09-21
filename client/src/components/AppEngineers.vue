<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import type { Engineer } from '@/types/entities.ts'
import { ref, watch } from 'vue'
import { SKILL_TYPE_MAP, VEHICLE_TYPE_MAP } from '@/utils/consts.ts'
import type { SkillType, VehicleType } from '@/types/utils.ts'
import { useCurrentStateStore } from '@/stores/state.ts'

interface IProps {
  loading: boolean
  engineers: Engineer[]
}

const props = defineProps<IProps>()

const store = useCurrentStateStore()

const engineers = ref<Engineer[]>([])

watch(
  () => [...props.engineers],
  (nVal) => {
    engineers.value = nVal
  },
)

const getVehicleTypeTranslation = (type: string): string => {
  if (!Object.keys(VEHICLE_TYPE_MAP).includes(type)) return 'Неизвестно'
  return VEHICLE_TYPE_MAP[type as VehicleType]
}

const getSkillTranslation = (type: string): string => {
  if (!Object.keys(SKILL_TYPE_MAP).includes(type)) return 'Неизвестно'
  return SKILL_TYPE_MAP[type as SkillType]
}

const getSubtitle = (item: Engineer): string => {
  return `${getVehicleTypeTranslation(item.vehicle_type)} • ${item.available_from} - ${item.available_until}`
}

const getColor = (item: Engineer): string => {
  const hashString = (str: string): number => {
    let hash = 2166136248
    for (let i = 0; i < str.length; i++) {
      hash ^= str.charCodeAt(i)
      hash = Math.imul(hash, 16777619)
    }
    return hash >>> 0
  }
  const hash = hashString(item.id)
  const hue = (hash * 0.61803398875 * 360) % 360

  const saturation = 60 + (hash % 3) * 10
  const lightness = 45 + ((hash >> 4) % 3) * 10

  return `hsl(${hue.toFixed(1)}, ${saturation}%, ${lightness}%)`
}
</script>

<template>
  <basic-card title="Список работников" :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <v-list class="overflow-list" density="compact">
      <v-list-group
        v-for="item in engineers"
        :key="item.id"
        :model-value="store.getExpandedEngineerIds.includes(item.id)"
        @update:model-value="() => store.toggleExpandedEngineer(item.id)"
      >
        <template #activator="{ props: activatorProps }">
          <v-list-item v-bind="activatorProps" :title="item.name" :subtitle="getSubtitle(item)">
            <template #prepend>
              <v-avatar :color="getColor(item)"></v-avatar>
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
