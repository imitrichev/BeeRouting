<script setup lang="ts">
import BasicCard from '@/templates/BasicCard.vue'

import IconButton from '@/templates/IconButton.vue'
import { useSelectorsStore } from '@/stores/selectors.ts'
import { computed, ref, watch } from 'vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import ApplyDialog from '@/templates/ApplyDialog.vue'

interface IProps {
  loading: boolean
}

const props = defineProps<IProps>()

const selectorsStore = useSelectorsStore()
const districtDataStore = useDistrictDataStore()

const territoriesSelectorItems = computed(() => selectorsStore.territories)
const territoriesSelectorValue = ref<string | null>(null)

const loadingDistrictData = computed(() => districtDataStore.loadingDistrictData)

const resetDatasetsDialogOpened = ref<boolean>(false)
const loadingResetAllDatasets = computed(() => districtDataStore.loadingResetAllDatasets)

const optimizationDialogOpened = ref<boolean>(false)
const ignoreTaskStatuses = ref<boolean>(true)
const loadingOptimization = computed(() => districtDataStore.loadingOptimization)

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
  ignoreTaskStatuses.value = true
  optimizationDialogOpened.value = true
}

const closeOptimizationDialog = async (applied: boolean) => {
  if (!applied) {
    optimizationDialogOpened.value = false
    return
  }
  await districtDataStore.optimizeDataset(ignoreTaskStatuses.value)
  optimizationDialogOpened.value = false
}
</script>

<template>
  <basic-card :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <v-row no-gutters class="px-4 py-3">
      <v-select
        v-model="territoriesSelectorValue"
        :items="territoriesSelectorItems"
        variant="outlined"
        item-value="code"
        item-title="name"
        label="Район"
        hide-details
        :loading="loadingDistrictData"
        max-width="150"
      ></v-select>
      <icon-button
        tooltip-text="Сбросить изменения"
        class="ml-3 my-2"
        icon="restart_alt"
        color="red"
        :loading="loadingDistrictData"
        @click="openResetDatasetsDialog"
      />
      <icon-button
        tooltip-text="Назначить заявки"
        class="mr-3 my-2"
        icon="alt_route"
        :loading="loadingDistrictData"
        @click="openOptimizationDialog"
      />
    </v-row>
  </basic-card>
  <apply-dialog
    v-if="resetDatasetsDialogOpened"
    :loading="loadingResetAllDatasets"
    text="Вы уверены, что хотите сбросить совершённые действия над всеми районами и вернуть данные к исходному состоянию? Это действие будет невозможно отменить."
    @close="closeResetDatasetsDialog"
  />
  <apply-dialog
    v-if="optimizationDialogOpened"
    :loading="loadingOptimization"
    text="Вы уверены, что хотите начать процесс назначения заявок?"
    @close="closeOptimizationDialog"
  >
    <!--    <v-card class="rounded-lg mt-2 mx-2">-->
    <!--      <v-checkbox-->
    <!--        v-model="ignoreTaskStatuses"-->
    <!--        label="Игнорировать текущие статусы заявок"-->
    <!--        class="px-2 py-1"-->
    <!--        hide-details-->
    <!--      />-->
    <!--    </v-card>-->
  </apply-dialog>
</template>
<style scoped lang="scss"></style>
