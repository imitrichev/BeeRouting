<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'

import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed } from 'vue'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()
const metrics = computed(() => districtDataStore.getMetrics)
</script>

<template>
  <basic-card :loading="props.loading" title="Метрики распределения">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <v-row no-gutters v-if="metrics && !props.loading">
      <v-col cols="12" class="fill-height">
        <v-card color="blue-lighten-5 fill-height" class="rounded-0 elevation-0" variant="flat">
          <v-card-text>
            Инженеров: <br />
            <strong>{{ metrics.used_engineers_count }}</strong>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" class="fill-height">
        <v-card color="green-lighten-5 fill-height" class="rounded-0 elevation-0" variant="flat">
          <v-card-text>
            Задач: <br />
            <strong>{{ metrics.assigned_task_count }}</strong>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" class="fill-height">
        <v-card color="red-lighten-5 fill-height" class="rounded-0 elevation-0" variant="flat">
          <v-card-text>
            Пробег, км: <br />
            <strong>{{ metrics.total_distance_km.toFixed(1) }}</strong>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" class="fill-height">
        <v-card color="purple-lighten-5 fill-height" class="rounded-0 elevation-0" variant="flat">
          <v-card-text>
            Objective: <br />
            <strong>{{ metrics.total_objective }}</strong>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </basic-card>
</template>
<style scoped lang="scss"></style>
