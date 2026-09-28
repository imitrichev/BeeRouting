<script setup lang="ts">
/**
 * Корневой компонент приложения.
 *
 * Отвечает за компоновку страницы: шапка, строка управления, метрики
 * оптимизации, карта, задачи, неназначенные задачи, таблица маршрутов
 * и список инженеров.
 *
 * При монтировании инициирует загрузку всех справочников через `selectorsStore`.
 * Блоки `optimization-metrics`, `unassigned-tasks` и `routes-table` рендерятся
 * только при наличии результата оптимизации (`districtDataStore.isOptimized`).
 */

import AppHeader from '@/components/AppHeader.vue'
import ControlRow from '@/components/ControlRow.vue'
import AppTasks from '@/components/AppTasks.vue'
import AppEngineers from '@/components/AppEngineers.vue'
import AppMap from '@/components/AppMap.vue'
import { onMounted } from 'vue'
import { useSelectorsStore } from '@/stores/selectors.ts'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import OptimizationMetrics from '@/components/OptimizationMetrics.vue'
import RoutesTable from '@/components/RoutesTable.vue'
import UnassignedTasks from '@/components/UnassignedTasks.vue'

const selectorsStore = useSelectorsStore()
const districtDataStore = useDistrictDataStore()

/**
 * Предзагружает все справочники, необходимые для работы фильтров и форм.
 */
onMounted(() => {
  selectorsStore.loadTerritories()
  selectorsStore.loadDistricts()
  selectorsStore.loadPriorities()
  selectorsStore.loadSkills()
  selectorsStore.loadTimeNorms()
  selectorsStore.loadVehicleTypes()
})
</script>

<template>
  <v-app>
    <app-header />
    <v-main class="main-container px-4 py-3">
      <v-row no-gutters class="justify-center">
        <v-row no-gutters class="row-container">
          <v-col cols="12">
            <v-row no-gutters>
              <v-col cols="12" class="mb-3">
                <control-row :loading="selectorsStore.loadingTerritories" />
              </v-col>
            </v-row>
            <v-row no-gutters>
              <!-- Метрики оптимизации: показываются только после расчёта -->
              <v-col cols="12" v-if="districtDataStore.isOptimized" class="mb-3">
                <optimization-metrics
                  :loading="
                    selectorsStore.loadingTerritories ||
                    districtDataStore.loadingDistrictData ||
                    districtDataStore.loadingOptimization
                  "
                />
              </v-col>

              <!-- Карта маршрутов -->
              <v-col cols="12" class="mb-3">
                <app-map
                  :loading="
                    selectorsStore.loadingTerritories || districtDataStore.loadingDistrictData
                  "
                />
              </v-col>

              <!-- Список задач -->
              <v-col cols="12" class="mb-3 fill-height">
                <app-tasks
                  :loading="
                    selectorsStore.loadingTerritories || districtDataStore.loadingDistrictData
                  "
                />
              </v-col>

              <!-- Блоки, доступные только после оптимизации -->
              <template v-if="districtDataStore.isOptimized">
                <v-col cols="12" class="mb-3">
                  <unassigned-tasks
                    :loading="
                      selectorsStore.loadingTerritories ||
                      districtDataStore.loadingDistrictData ||
                      districtDataStore.loadingOptimization
                    "
                  />
                </v-col>
                <v-col cols="12" class="mb-3">
                  <routes-table
                    :loading="
                      selectorsStore.loadingTerritories ||
                      districtDataStore.loadingDistrictData ||
                      districtDataStore.loadingOptimization
                    "
                  />
                </v-col>
              </template>

              <!-- Список инженеров -->
              <v-col cols="12" class="mb-3 fill-height">
                <app-engineers
                  :loading="
                    selectorsStore.loadingTerritories || districtDataStore.loadingDistrictData
                  "
                />
              </v-col>
            </v-row>
          </v-col>
        </v-row>
      </v-row>
    </v-main>
  </v-app>
</template>

<style lang="scss">
/**
 * Основной контейнер страницы.
 * Занимает всю высоту вьюпорта за вычетом высоты шапки (66px),
 * скроллится по вертикали и горизонтали с тонким кастомным скроллбаром.
 */
.main-container {
  margin-top: 66px !important;
  padding-top: 12px !important;
  height: calc(100vh - 66px) !important;
  max-height: calc(100vh - 66px) !important;
  width: 100% !important;
  min-width: 0 !important;
  overflow-x: auto;
  overflow-y: auto !important;

  // Firefox
  scrollbar-width: thin;
  scrollbar-color: rgba(var(--v-theme-on-surface), 0.2) transparent;

  // WebKit (Chrome, Edge, Safari)
  &::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  &::-webkit-scrollbar-button {
    display: none;
    width: 0;
    height: 0;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
    margin: 4px 0;
  }

  &::-webkit-scrollbar-thumb {
    background-color: rgba(var(--v-theme-on-surface), 0.2);
    border-radius: 999px;
    border: 2px solid transparent;
    background-clip: content-box;
    transition: background-color 0.2s ease;
  }

  &::-webkit-scrollbar-thumb:hover {
    background-color: rgba(var(--v-theme-on-surface), 0.4);
  }

  &::-webkit-scrollbar-corner {
    background: transparent;
  }
}

/**
 * Разрешает внутренним Vuetify-элементам сжиматься внутри flex-контейнера,
 * предотвращая переполнение по горизонтали.
 */
.main-container :deep(.v-row),
.main-container :deep(.v-col),
.main-container :deep(.v-card),
.main-container :deep(.v-table__wrapper) {
  min-width: 0;
}

/**
 * Ограничивает ширину основного ряда контента для широких экранов.
 */
.row-container {
  max-width: 1920px !important;
  width: 100%;
}
</style>
