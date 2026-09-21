<script setup lang="ts">
import AppHeader from "@/components/AppHeader.vue";
import FileUpload from "@/components/FileUpload.vue";
import AppTasks from "@/components/AppTasks.vue";
import AppWorkers from "@/components/AppWorkers.vue";
import AppMap from "@/components/AppMap.vue";
import { useDisplay } from "vuetify/framework";
import { useDefaultDatasetStore } from "@/stores";
import { storeToRefs } from "pinia";
import { onMounted } from "vue";

const display = useDisplay()
const defaultDatasetStore = useDefaultDatasetStore()
const { getData, getLoading } = storeToRefs(defaultDatasetStore)

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
                <file-upload />
              </v-col>
            </v-row>
            <v-row no-gutters>
              <v-col cols="12" md="5" xl="6">
                <v-row no-gutters>
                  <v-col cols="12" xl="6" class="mb-3" :class="display.mdAndUp.value ? 'pr-3' : ''">
                    <app-tasks />
                  </v-col>
                  <v-col cols="12" xl="6" class="mb-3" :class="display.mdAndUp.value ? 'pr-3' : ''">
                    <app-workers />
                  </v-col>
                </v-row>
              </v-col>
              <v-col cols="12" md="7" xl="6" class="mb-3">
                <app-map />
                {{ getData }}
                {{ getLoading }}
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
  margin-top: 66px!important;
  padding-top: 12px!important;
  height: calc(100vh - 66px)!important;
  max-height: calc(100vh - 66px)!important;
  overflow-y: auto!important;
}

.row-container {
  max-width: 1920px!important;
}
</style>
