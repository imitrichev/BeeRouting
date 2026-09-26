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
      v-if="unassigned.length === 0"
      type="success"
      class="d-flex align-center justify-center text-medium-emphasis py-4 rounded-0"
    >
      Все заявки успешно распределены
    </v-alert>

    <v-list v-else class="overflow-list" density="compact">
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
.overflow-list {
  min-height: unset !important;
}
</style>
