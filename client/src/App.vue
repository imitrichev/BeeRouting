<script setup lang="ts">
import AppHeader from '@/components/AppHeader.vue'
import ControlRow from '@/components/ControlRow.vue'
import AppTasks from '@/components/AppTasks.vue'
import AppEngineers from '@/components/AppEngineers.vue'
import AppMap from '@/components/AppMap.vue'
import { useDisplay } from 'vuetify/framework'
import { useDefaultDatasetStore, useOptimizationStore } from '@/stores'
import { storeToRefs } from 'pinia'
import { computed, onMounted, watch } from 'vue'
import type { Engineer, Task } from '@/types/entities.ts'
import { useCurrentStateStore } from '@/stores/state.ts'

const display = useDisplay()
const defaultDatasetStore = useDefaultDatasetStore()
const optimizationStore = useOptimizationStore()
const stateStore = useCurrentStateStore()
const { getLoading, getData } = storeToRefs(defaultDatasetStore)

const getEngineers = computed((): Engineer[] => {
  if (!getData.value) return []
  return getData.value.dataset.engineers
})

const getTasks = computed((): Task[] => {
  if (!getData.value) return []
  return getData.value.dataset.tasks
})

watch(
  () => getData.value,
  (nVal) => {
    if (!nVal) return
    stateStore.setTasks(nVal.dataset.tasks)
    stateStore.setEngineers(nVal.dataset.engineers)
    stateStore.setScenarioName(nVal.dataset.scenario_name)
    stateStore.setSourceName(nVal.dataset.source_name)
  },
)

watch(
  () => optimizationStore.getData,
  (nVal) => {
    if (!nVal) return
    stateStore.setOptimizationResult(nVal.result)
    stateStore.setTasks(nVal.dataset.tasks)
    stateStore.setEngineers(nVal.dataset.engineers)
    stateStore.setSourceName(nVal.dataset.source_name)
    stateStore.setScenarioName(nVal.dataset.scenario_name)
  },
)

onMounted(() => {
  defaultDatasetStore.execute({})
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
                <control-row :loading="getLoading" />
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
                    <app-tasks :loading="getLoading" :tasks="getTasks" />
                  </v-col>
                  <v-col
                    cols="12"
                    xl="6"
                    class="mb-3 fill-height"
                    :class="display.mdAndUp.value ? 'pr-3' : ''"
                  >
                    <app-engineers :loading="getLoading" :engineers="getEngineers" />
                  </v-col>
                </v-row>
              </v-col>
              <v-col cols="12" md="7" xl="6" class="mb-3">
                <app-map :loading="getLoading" />
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
  min-width: unset !important;
  width: unset !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
}

.row-container {
  max-width: 1920px !important;
}
</style>
