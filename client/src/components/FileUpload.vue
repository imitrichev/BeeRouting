<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import { useDefaultDatasetStore, useOptimizationStore } from '@/stores'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()
const defaultDatasetStore = useDefaultDatasetStore()
const optimizationsStore = useOptimizationStore()

const reloadDefaultDataset = () => {
  defaultDatasetStore.execute({})
}

const optimizeResult = () => {
  optimizationsStore.execute({})
}
</script>

<template>
  <basic-card :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <v-tooltip text="Загрузить оф. датасет">
      <template #activator="{ props }">
        <v-btn
          v-bind="props"
          class="ml-3 my-2"
          icon="restart_alt"
          size="40"
          flat
          :loading="optimizationsStore.getLoading || defaultDatasetStore.getLoading"
          @click="reloadDefaultDataset"
        />
      </template>
    </v-tooltip>
    <v-tooltip text="Оптимизировать">
      <template #activator="{ props }">
        <v-btn
          v-bind="props"
          class="mr-3 my-2"
          icon="alt_route"
          size="40"
          flat
          :loading="optimizationsStore.getLoading || defaultDatasetStore.getLoading"
          @click="optimizeResult"
        />
      </template>
    </v-tooltip>
  </basic-card>
</template>
<style scoped lang="scss"></style>
