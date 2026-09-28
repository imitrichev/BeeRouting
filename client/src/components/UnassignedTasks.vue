<script setup lang="ts">
/**
 * Карточка со списком неназначенных заявок.
 *
 * Показывает задачи, которые не удалось назначить при оптимизации, вместе
 * с причиной (сообщением от API). Если неназначенных задач нет — выводится
 * информационное сообщение об успешном распределении.
 */

import BasicCard from '@/templates/BasicCard.vue'
import type { UnassignedTask } from '@/types/entities.ts'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import { computed } from 'vue'

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Флаг загрузки: переключает карточку в состояние скелетона. */
  loading: boolean
}

const props = defineProps<IProps>()

const districtDataStore = useDistrictDataStore()

/** Список неназначенных задач из результата оптимизации. */
const unassigned = computed<UnassignedTask[]>(() => districtDataStore.getUnassigned)
</script>

<template>
  <basic-card :loading="props.loading" title="Неназначенные заявки">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>

    <!-- Все заявки распределены -->
    <v-alert
      v-if="unassigned.length === 0 && !props.loading"
      class="d-flex align-center justify-center text-medium-emphasis py-4 rounded-0"
    >
      Все заявки успешно распределены
    </v-alert>

    <!-- Список неназначенных заявок -->
    <v-list v-else-if="!props.loading" class="overflow-list default-scrollbar" density="compact">
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
/**
 * Переопределяет высоту контейнера скролла из глобальных стилей `.overflow-list`
 * под компактный список неназначенных заявок.
 */
.overflow-list {
  max-height: 200px !important;
  min-height: unset !important;
}
</style>
