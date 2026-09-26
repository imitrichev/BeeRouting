<script setup lang="ts">
import AppHeader from '@/components/AppHeader.vue'
import ControlRow from '@/components/ControlRow.vue'
import AppTasks from '@/components/AppTasks.vue'
import AppEngineers from '@/components/AppEngineers.vue'
import AppMap from '@/components/AppMap.vue'
import { useDisplay } from 'vuetify/framework'
import { onMounted } from 'vue'
import { useSelectorsStore } from '@/stores/selectors.ts'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import OptimizationMetrics from '@/components/OptimizationMetrics.vue'
import RoutesTable from '@/components/RoutesTable.vue'
import UnassignedTasks from '@/components/UnassignedTasks.vue'

const display = useDisplay()
const selectorsStore = useSelectorsStore()
const districtDataStore = useDistrictDataStore()

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
            <v-row no-gutters v-if="districtDataStore.isOptimized">
              <v-col cols="12" class="mb-3">
                <optimization-metrics
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
              <v-col cols="12" class="mb-3">
                <unassigned-tasks
                  :loading="
                    selectorsStore.loadingTerritories ||
                    districtDataStore.loadingDistrictData ||
                    districtDataStore.loadingOptimization
                  "
                />
              </v-col>
            </v-row>
            <v-row no-gutters>
              <v-col cols="12" md="5" xl="6">
                <v-row no-gutters>
                  <v-col
                    cols="12"
                    xl="6"
                    class="mb-3 fill-height"
                    :class="display.mdAndUp.value ? 'pr-3' : ''"
                  >
                    <app-tasks
                      :loading="
                        selectorsStore.loadingTerritories || districtDataStore.loadingDistrictData
                      "
                    />
                  </v-col>
                  <v-col
                    cols="12"
                    xl="6"
                    class="mb-3 fill-height"
                    :class="display.mdAndUp.value ? 'pr-3' : ''"
                  >
                    <app-engineers
                      :loading="
                        selectorsStore.loadingTerritories || districtDataStore.loadingDistrictData
                      "
                    />
                  </v-col>
                </v-row>
              </v-col>
              <v-col cols="12" md="7" xl="6" class="mb-3">
                <app-map
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
.main-container {
  margin-top: 66px !important;
  padding-top: 12px !important;
  height: calc(100vh - 66px) !important;
  max-height: calc(100vh - 66px) !important;
  width: 100% !important;
  min-width: 0 !important;
  overflow-x: auto;
  overflow-y: auto !important;

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

.main-container :deep(.v-row),
.main-container :deep(.v-col),
.main-container :deep(.v-card),
.main-container :deep(.v-table__wrapper) {
  min-width: 0;
}

.row-container {
  max-width: 1920px !important;
  width: 100%;
}
</style>
