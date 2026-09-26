import { defineStore } from 'pinia'
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { sendRequest } from '@/utils/requests.ts'
import baseUrls from '@/urls'
import type {
  DistrictData,
  Engineer,
  EngineerRoute,
  OptimizationMetrics,
  Task,
  UnassignedTask,
} from '@/types/entities.ts'

export const useDistrictDataStore = defineStore('districtData', () => {
  const districtCode = ref<string | null>(null)
  const loadingDistrictData = ref<boolean>(true)
  const districtData = shallowRef<DistrictData | null>(null)
  const selectedRoutes = ref<string[]>([])

  const isOptimized = computed((): boolean => {
    return !!districtData.value && !!districtData.value.result
  })

  const getDistrictData = computed((): DistrictData | null => {
    return districtData.value
  })

  const getDistrictTasks = computed((): Task[] => {
    if (!districtData.value) return []
    return districtData.value.dataset.tasks
  })

  const getDistrictEngineers = computed((): Engineer[] => {
    if (!districtData.value) return []
    return districtData.value.dataset.engineers
  })

  const getRoutes = computed((): EngineerRoute[] => {
    if (!districtData.value) return []
    if (!districtData.value.result) return []
    return districtData.value.result.routes
  })

  const getDistanceByEngineer = computed((): Record<string, number> => {
    if (!districtData.value) return {}
    if (!districtData.value.result) return {}
    return districtData.value.result.distance_by_engineer
  })

  const getMetrics = computed((): OptimizationMetrics | null => {
    if (!districtData.value) return null
    if (!districtData.value.result) return null
    return districtData.value.result.metrics
  })

  const getTravelTimeByEngineer = computed((): Record<string, number> => {
    if (!districtData.value) return {}
    if (!districtData.value.result) return {}
    return districtData.value.result.travel_time_by_engineer
  })

  const getUnassigned = computed((): UnassignedTask[] => {
    if (!districtData.value) return []
    if (!districtData.value.result) return []
    return districtData.value.result.unassigned
  })

  const loadDistrictData = async () => {
    loadingDistrictData.value = true
    const response = await sendRequest<DistrictData>(
      baseUrls.DISTRICT.DATA,
      {},
      {},
      { territory: String(districtCode.value) },
    )
    if (response.isSuccess) {
      districtData.value = response.data
      selectedRoutes.value = getRoutes.value.map((r) => r.engineer_id)
      loadingDistrictData.value = false
    }
  }

  const loadingResetAllDatasets = ref<boolean>(false)

  const resetAllDatasets = async () => {
    loadingResetAllDatasets.value = true
    await sendRequest(baseUrls.RESET_ALL)
    loadingResetAllDatasets.value = false
  }

  const loadingOptimization = ref<boolean>(false)

  const optimizeDataset = async (ignoreTaskStatuses: boolean) => {
    loadingOptimization.value = true
    const response = await sendRequest<DistrictData>(
      baseUrls.DISTRICT.OPTIMIZE,
      { ignore_task_statuses: ignoreTaskStatuses },
      {},
      { territory: String(districtCode.value) },
    )
    if (response.isSuccess) {
      districtData.value = response.data
      selectedRoutes.value = getRoutes.value.map((r) => r.engineer_id)
    }

    loadingOptimization.value = false
  }

  const selectDistrict = (code: string) => {
    districtCode.value = code
  }

  const toggleRouteSelection = (engineerId: string) => {
    const i = selectedRoutes.value.indexOf(engineerId)
    if (i === -1) selectedRoutes.value.push(engineerId)
    else selectedRoutes.value.splice(i, 1)
  }

  const isRouteSelected = (engineerId: string) => selectedRoutes.value.includes(engineerId)

  const clearRouteSelection = () => {
    selectedRoutes.value = []
  }

  watch(districtCode, async (nVal) => {
    if (!nVal) return
    await nextTick()
    await loadDistrictData()
  })

  return {
    selectDistrict,
    loadDistrictData,
    loadingDistrictData,
    getDistrictData,

    getDistrictTasks,
    getDistrictEngineers,

    resetAllDatasets,
    loadingResetAllDatasets,

    loadingOptimization,
    optimizeDataset,
    isOptimized,

    getRoutes,
    getDistanceByEngineer,
    getMetrics,
    getTravelTimeByEngineer,
    getUnassigned,
    selectedRoutes,
    toggleRouteSelection,
    isRouteSelected,
    clearRouteSelection,
  }
})
