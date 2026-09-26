<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import type { UnassignedTask } from '@/types/entities.ts'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed } from 'vue'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()
const unassigned = computed<UnassignedTask[]>(() => districtDataStore.getUnassigned)
</script>

<template>
  <basic-card :loading="props.loading" title="Неназначенные">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>

    <v-alert
      v-if="unassigned.length === 0 && !props.loading"
      class="d-flex align-center justify-center text-medium-emphasis py-4 rounded-0 data-height alert-height"
    >
      Все заявки успешно распределены
    </v-alert>

    <v-list v-else-if="!props.loading" class="overflow-list data-height" density="compact">
      <v-list-item
        v-for="item in unassigned"
        :key="item.task_id"
        :title="item.task_id"
        :subtitle="item.message"
      />
    </v-list>
  </basic-card>
</template>

<style scoped lang="scss">
.data-height {
  height: calc(72px * 4) !important;
  min-height: calc(72px * 4) !important;
  max-height: calc(72px * 4) !important;
}

.alert-height {
  @media (max-width: 839px) {
    height: auto !important;
    min-height: unset !important;
    max-height: unset !important;
  }
}
</style>
