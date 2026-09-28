<script setup lang="ts">
/**
 * Панель управления районом.
 *
 * Содержит:
 * - селектор района (территории) с автозагрузкой данных при выборе;
 * - кнопки «Сбросить изменения», «Перепланирование» (видна только после
 *   оптимизации) и «Назначить заявки»;
 * - на десктопе (`mdAndUp`) — текстовые кнопки, на мобильных — иконки с тултипами;
 * - модальные диалоги: подтверждение сброса, оптимизация, перепланирование
 *   и информационный диалог о перепланировании.
 */

import BasicCard from '@/templates/BasicCard.vue'

import IconButton from '@/templates/IconButton.vue'
import { useSelectorsStore } from '@/stores/selectors.ts'
import { computed, ref, watch } from 'vue'
import { useDistrictDataStore } from '@/stores/districtData.ts'
import ApplyDialog from '@/templates/ApplyDialog.vue'
import OptimizationDialog from '@/components/modals/OptimizationDialog.vue'
import ReplanDialog from '@/components/modals/ReplanDialog.vue'
import { useDisplay } from 'vuetify'
import ReplanInfoDialog from '@/components/modals/ReplanInfoDialog.vue'

/**
 * Пропсы компонента.
 */
interface IProps {
  /** Флаг загрузки: переключает карточку в состояние скелетона. */
  loading: boolean
}

const props = defineProps<IProps>()

const selectorsStore = useSelectorsStore()
const districtDataStore = useDistrictDataStore()

/** Реактивные брейкпоинты Vuetify. */
const { mdAndUp } = useDisplay()

/** `true`, если для текущего района есть результат оптимизации. */
const isOptimized = computed(() => districtDataStore.isOptimized)

/** Список территорий для селектора. */
const territoriesSelectorItems = computed(() => selectorsStore.territories)
/** Текущее выбранное значение территории. */
const territoriesSelectorValue = ref<string | null>(null)

/** Флаг загрузки данных района. */
const loadingDistrictData = computed(() => districtDataStore.loadingDistrictData)

/** Флаг открытия диалога сброса датасетов. */
const resetDatasetsDialogOpened = ref<boolean>(false)
/** Флаг выполнения полного сброса датасетов. */
const loadingResetAllDatasets = computed(() => districtDataStore.loadingResetAllDatasets)

/** Флаг открытия диалога оптимизации. */
const optimizationDialogOpened = ref<boolean>(false)
/** Флаг открытия диалога перепланирования. */
const replanDialogOpened = ref<boolean>(false)
/** Флаг открытия информационного диалога о перепланировании. */
const replanInfoDialogOpened = ref<boolean>(false)

/**
 * При первой загрузке справочника территорий автоматически выбирает первую территорию.
 */
watch(territoriesSelectorItems, (nVal) => {
  if (!nVal.length || !nVal[0]) return
  territoriesSelectorValue.value = nVal[0].code
})

/**
 * При смене выбранной территории сообщает об этом стору данных района.
 * Стор сам инициирует загрузку через `watch` на `districtCode`.
 */
watch(territoriesSelectorValue, (nVal) => {
  if (!nVal) return
  districtDataStore.selectDistrict(nVal)
})

/** Открывает диалог подтверждения сброса датасетов. */
const openResetDatasetsDialog = () => {
  resetDatasetsDialogOpened.value = true
}

/**
 * Обрабатывает закрытие диалога сброса.
 * При подтверждении выполняет полный сброс и перезагружает данные района.
 *
 * @param applied `true`, если пользователь подтвердил сброс.
 */
const closeResetDatasetsDialog = async (applied: boolean) => {
  if (!applied) {
    resetDatasetsDialogOpened.value = false
    return
  }
  await districtDataStore.resetAllDatasets()
  resetDatasetsDialogOpened.value = false
  await districtDataStore.loadDistrictData()
}

/** Открывает диалог оптимизации. */
const openOptimizationDialog = () => {
  optimizationDialogOpened.value = true
}

/** Закрывает диалог оптимизации. */
const closeOptimizationDialog = async () => {
  optimizationDialogOpened.value = false
}

/** Открывает диалог перепланирования. */
const openReplanDialog = () => {
  replanDialogOpened.value = true
}

/**
 * Обрабатывает закрытие диалога перепланирования.
 * При подтверждении открывает информационный диалог о результате.
 *
 * @param applied `true`, если пользователь применил перепланирование.
 */
const closeReplanDialog = async (applied: boolean) => {
  replanDialogOpened.value = false
  if (applied) replanInfoDialogOpened.value = true
}

/** Закрывает информационный диалог о перепланировании. */
const closeReplanInfoDialog = () => {
  replanInfoDialogOpened.value = false
}
</script>

<template>
  <basic-card :loading="props.loading">
    <template #loading>
      <v-skeleton-loader type="list-item-two-line" />
    </template>
    <v-row no-gutters class="px-4 py-3 align-center">
      <!-- Селектор района -->
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

      <!-- Десктоп: текстовые кнопки -->
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
          v-if="isOptimized"
          variant="text"
          :loading="loadingDistrictData"
          prepend-icon="autorenew"
          color="warning"
          class="px-3"
          @click="openReplanDialog"
        >
          Перепланирование
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

      <!-- Мобильные: иконки с тултипами -->
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
          tooltip-text="Перепланирование"
          icon="autorenew"
          color="warning"
          :loading="loadingDistrictData"
          @click="openReplanDialog"
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

  <!-- Диалог подтверждения полного сброса -->
  <apply-dialog
    v-if="resetDatasetsDialogOpened"
    :loading="loadingResetAllDatasets"
    text="Вы уверены, что хотите сбросить совершённые действия над всеми районами и вернуть данные к исходному состоянию? Это действие будет невозможно отменить."
    @close="closeResetDatasetsDialog"
  />

  <!-- Диалоги оптимизации и перепланирования -->
  <optimization-dialog :opened="optimizationDialogOpened" @close="closeOptimizationDialog" />
  <replan-dialog :opened="replanDialogOpened" @close="closeReplanDialog" />
  <replan-info-dialog :opened="replanInfoDialogOpened" @close="closeReplanInfoDialog" />
</template>

<style scoped lang="scss"></style>
