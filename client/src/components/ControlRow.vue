<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'

import IconButton from '@/templates/IconButton.vue'
import { useSelectorsStore } from '@/stores/selectors.ts'
import { computed, ref, watch } from 'vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import ApplyDialog from '@/templates/ApplyDialog.vue'
import OptimizationDialog from '@/components/modals/OptimizationDialog.vue'
import { useDisplay } from 'vuetify'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const selectorsStore = useSelectorsStore()
const districtDataStore = useDistrictDataStore()

const { mdAndUp } = useDisplay()

const territoriesSelectorItems = computed(() => selectorsStore.territories)
const territoriesSelectorValue = ref<string | null>(null)

const loadingDistrictData = computed(() => districtDataStore.loadingDistrictData)

const resetDatasetsDialogOpened = ref<boolean>(false)
const loadingResetAllDatasets = computed(() => districtDataStore.loadingResetAllDatasets)

const optimizationDialogOpened = ref<boolean>(false)

watch(territoriesSelectorItems, (nVal) => {
  if (!nVal.length || !nVal[0]) return
  territoriesSelectorValue.value = nVal[0].code
})

watch(territoriesSelectorValue, (nVal) => {
  if (!nVal) return
  districtDataStore.selectDistrict(nVal)
})

const openResetDatasetsDialog = () => {
  resetDatasetsDialogOpened.value = true
}

const closeResetDatasetsDialog = async (applied: boolean) => {
  if (!applied) {
    resetDatasetsDialogOpened.value = false
    return
  }
  await districtDataStore.resetAllDatasets()
  resetDatasetsDialogOpened.value = false
  await districtDataStore.loadDistrictData()
}

const openOptimizationDialog = () => {
  optimizationDialogOpened.value = true
}

const closeOptimizationDialog = async () => {
  optimizationDialogOpened.value = false
}
</script>

<template>
  <basic-card :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <v-row no-gutters class="px-4 py-3 align-center">
      <v-select
        v-model="territoriesSelectorValue"
        :items="territoriesSelectorItems"
        item-value="code"
        item-title="name"
        label="Район"
        hide-details
        density="compact"
        variant="outlined"
        :loading="loadingDistrictData"
        max-width="300"
      />
      <v-spacer />

      <template v-if="mdAndUp">
        <v-btn
          variant="text"
          color="red"
          :loading="loadingDistrictData"
          prepend-icon="restart_alt"
          class="px-3"
          @click="openResetDatasetsDialog"
        >
          Сбросить изменения
        </v-btn>
        <v-btn
          variant="text"
          :loading="loadingDistrictData"
          prepend-icon="alt_route"
          class="px-3"
          @click="openOptimizationDialog"
        >
          Назначить заявки
        </v-btn>
      </template>

      <template v-else>
        <icon-button
          tooltip-text="Сбросить изменения"
          class="ml-3"
          icon="restart_alt"
          color="red"
          :loading="loadingDistrictData"
          @click="openResetDatasetsDialog"
        />
        <icon-button
          tooltip-text="Назначить заявки"
          icon="alt_route"
          :loading="loadingDistrictData"
          @click="openOptimizationDialog"
        />
      </template>
    </v-row>
  </basic-card>
  <apply-dialog
    v-if="resetDatasetsDialogOpened"
    :loading="loadingResetAllDatasets"
    text="Вы уверены, что хотите сбросить совершённые действия над всеми районами и вернуть данные к исходному состоянию? Это действие будет невозможно отменить."
    @close="closeResetDatasetsDialog"
  />
  <optimization-dialog :opened="optimizationDialogOpened" @close="closeOptimizationDialog" />
</template>
<style scoped lang="scss"></style>
