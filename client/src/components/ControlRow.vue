<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import { useDefaultDatasetStore, useOptimizationStore } from '@/stores'
import IconButton from '@/templates/IconButton.vue'

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
    <icon-button
      tooltip-text="Загрузить оф. датасет"
      class="ml-3 my-2"
      icon="restart_alt"
      :loading="optimizationsStore.getLoading || defaultDatasetStore.getLoading"
      @click="reloadDefaultDataset"
    />
    <icon-button
      tooltip-text="Оптимизировать"
      class="mr-3 my-2"
      icon="alt_route"
      :loading="optimizationsStore.getLoading || defaultDatasetStore.getLoading"
      @click="optimizeResult"
    />
  </basic-card>
</template>
<style scoped lang="scss"></style>
