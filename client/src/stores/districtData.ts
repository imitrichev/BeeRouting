import { defineStore } from 'pinia'
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { sendRequest } from '@/utils/requests.ts'
import baseUrls from '@/urls'
import type {
  DistrictData,
  Engineer,
  EngineerRoute,
  OptimizationMetrics,
  OptimizationRequestData,
  PreviewReassignmentObject,
  PreviewReassignmentRequestData,
  ReplanRequestData,
  RouteStopExplanationObject,
  Task,
  TaskCreateRequestData,
  TaskStatusUpdateRequestData,
  UnassignedTask,
} from '@/types/entities.ts'

export const useDistrictDataStore = defineStore('districtData', () => {
  const districtCode = ref<string | null>(null)
  const loadingDistrictData = ref<boolean>(true)
  const districtData = shallowRef<DistrictData | null>(null)
  const selectedRoutes = ref<string[]>([])
  const currentConsiderEquipment = ref<boolean>(true)

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

  const getDistrictEngineersSelector = computed(() =>
    getDistrictEngineers.value.map((item) => ({
      title: item.name,
      value: item.id,
    })),
  )

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
      currentConsiderEquipment.value = response.data.planning_options.consider_equipment
      clearRouteSelection()
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

  const optimizeDataset = async (data: OptimizationRequestData) => {
    loadingOptimization.value = true
    const response = await sendRequest<DistrictData>(
      baseUrls.DISTRICT.OPTIMIZE,
      data,
      {},
      { territory: String(districtCode.value) },
    )
    if (response.isSuccess) {
      districtData.value = response.data
      currentConsiderEquipment.value = data.consider_equipment
      clearRouteSelection()
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

  const loadingExplanation = ref<boolean>(false)
  const explanationTaskId = ref<string>('')
  const taskExplanation = ref<RouteStopExplanationObject | null>(null)

  const loadTaskExplanation = async (taskId: string) => {
    if (taskId === explanationTaskId.value) return
    explanationTaskId.value = taskId
    loadingExplanation.value = true
    const response = await sendRequest<RouteStopExplanationObject>(
      baseUrls.TASKS.EXPLAIN,
      {},
      { task_id: taskId },
      { territory: String(districtCode.value) },
    )
    if (taskId !== explanationTaskId.value) return
    if (!response.isSuccess) {
      taskExplanation.value = {
        task_id: taskId,
        explanation: 'Не удалось получить объяснение',
      }
      loadingExplanation.value = false
      return
    }
    taskExplanation.value = response.data
    loadingExplanation.value = false
  }

  const loadingManualReassignmentPreview = ref<boolean>(false)
  const manualReassignmentObject = ref<PreviewReassignmentObject | null>(null)

  const clearManualReassignmentPreview = () => {
    manualReassignmentObject.value = null
  }

  const loadManualReassignmentPreview = async (data: PreviewReassignmentRequestData) => {
    loadingManualReassignmentPreview.value = true
    const response = await sendRequest<PreviewReassignmentObject>(
      baseUrls.TASKS.REASSIGNMENT.PREVIEW,
      data,
      {},
      {
        territory: String(districtCode.value),
      },
    )

    if (!response.isSuccess) {
      manualReassignmentObject.value = response.data as unknown as PreviewReassignmentObject
    } else {
      manualReassignmentObject.value = response.data
    }

    loadingManualReassignmentPreview.value = false
  }

  const loadingManualReassignment = ref<boolean>(false)

  const loadManualReassignment = async () => {
    if (!manualReassignmentObject.value || !manualReassignmentObject.value.feasible) return
    loadingManualReassignment.value = true

    const response = await sendRequest<DistrictData>(
      baseUrls.TASKS.REASSIGNMENT.CONFIRM,
      {
        proposal_id: manualReassignmentObject.value.proposal_id,
      },
      {},
      {
        territory: String(districtCode.value),
      },
    )

    if (response.isSuccess) {
      districtData.value = response.data
      clearRouteSelection()
    }

    loadingManualReassignment.value = false
  }

  const loadingReplan = ref<boolean>(false)
  const loadReplan = async (data: ReplanRequestData) => {
    loadingReplan.value = true
    const response = await sendRequest<DistrictData>(
      baseUrls.DISTRICT.REPLAN,
      data,
      {},
      { territory: String(districtCode.value) },
    )
    if (response.isSuccess) {
      districtData.value = response.data
      currentConsiderEquipment.value = data.consider_equipment
      clearRouteSelection()
    }
    loadingReplan.value = false
  }

  const loadingCreateTask = ref<boolean>(false)

  const loadCreateTask = async (data: TaskCreateRequestData) => {
    loadingCreateTask.value = true
    const response = await sendRequest<DistrictData>(
      baseUrls.TASKS.CREATE,
      data,
      {},
      { territory: String(districtCode.value) },
    )
    if (response.isSuccess) {
      districtData.value = response.data
    }
    loadingCreateTask.value = false
  }

  const loadingUpdateTaskStatus = ref<boolean>(false)

  const loadUpdateTaskStatus = async (data: TaskStatusUpdateRequestData) => {
    loadingUpdateTaskStatus.value = true
    const response = await sendRequest<DistrictData>(
      baseUrls.TASKS.UPDATE_STATUS,
      data,
      {},
      { territory: String(districtCode.value) },
    )
    if (response.isSuccess) {
      districtData.value = response.data
      clearRouteSelection()
    }
    loadingUpdateTaskStatus.value = false
  }

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

    loadingExplanation,
    taskExplanation,
    loadTaskExplanation,

    getDistrictEngineersSelector,
    loadingManualReassignmentPreview,
    manualReassignmentObject,
    loadManualReassignmentPreview,
    clearManualReassignmentPreview,
    loadingManualReassignment,
    loadManualReassignment,

    currentConsiderEquipment,
    loadingReplan,
    loadReplan,

    loadingCreateTask,
    loadCreateTask,

    loadingUpdateTaskStatus,
    loadUpdateTaskStatus,
  }
})
