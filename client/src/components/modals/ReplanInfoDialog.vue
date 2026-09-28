<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'
import IconButton from '@/templates/IconButton.vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed } from 'vue'

interface IProps {
  opened: boolean
}

const props = defineProps<IProps>()

const emit = defineEmits<{
  close: []
}>()

const store = useDistrictDataStore()

const metrics = computed(() => store.getMetrics)
</script>

<template>
  <v-dialog :model-value="props.opened" max-width="480" persistent>
    <basic-card title="Результаты перепланирования">
      <template #toolbarAppend>
        <icon-button icon="close" class="ml-3" tooltip-text="Закрыть" @click="emit('close')" />
      </template>

      <v-row v-if="metrics" no-gutters class="flex-column px-4 py-4">
        <div class="metric-row">
          <span class="metric-label">Переназначено заявок</span>
          <span class="metric-value">{{ metrics.reassigned_task_count }}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Изменён порядок</span>
          <span class="metric-value">{{ metrics.reordered_task_count }}</span>
        </div>
      </v-row>

      <v-row v-else no-gutters class="px-4 py-4">
        <v-alert type="info" variant="tonal" class="w-100">
          Нет данных о перепланировании.
        </v-alert>
      </v-row>
    </basic-card>
  </v-dialog>
</template>

<style scoped lang="scss">
.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));

  &:last-child {
    border-bottom: none;
  }
}

.metric-label {
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.metric-value {
  font-weight: 600;
  font-size: 1rem;
}
</style>
