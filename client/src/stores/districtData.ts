/**
 * Pinia-стор данных района: загрузка датасета, запуск оптимизации,
 * перепланирование, ручное переназначение, создание задач и обновление
 * их статусов, а также вспомогательные computed-селекторы и состояние
 * выделения маршрутов.
 *
 * Стор выступает единой точкой доступа к `DistrictData` для компонентов
 * карты, списков и панелей метрик. При успешных мутирующих операциях
 * (оптимизация, replan, переназначение, обновление статуса) стор обновляет
 * `districtData` целиком и сбрасывает выделение маршрутов.
 */

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

/**
 * Стор данных района.
 */
export const useDistrictDataStore = defineStore('districtData', () => {
  // --- Базовое состояние --------------------------------------------------

  /** Код выбранной территории (района). */
  const districtCode = ref<string | null>(null)
  /** Флаг загрузки данных района. По умолчанию `true`, т.к. стор ждёт выбора территории. */
  const loadingDistrictData = ref<boolean>(true)
  /** Данные района (dataset + результат оптимизации). `shallowRef` для экономии на глубокой реактивности. */
  const districtData = shallowRef<DistrictData | null>(null)
  /** Идентификаторы инженеров, чьи маршруты выделены в UI. */
  const selectedRoutes = ref<string[]>([])
  /** Текущее значение опции «учитывать оборудование» (синхронизируется с данными района). */
  const currentConsiderEquipment = ref<boolean>(true)

  // --- Computed-селекторы -------------------------------------------------

  /** `true`, если для текущего района есть результат оптимизации. */
  const isOptimized = computed((): boolean => {
    return !!districtData.value && !!districtData.value.result
  })

  /** Текущие данные района или `null`. */
  const getDistrictData = computed((): DistrictData | null => {
    return districtData.value
  })

  /** Список задач района (пустой массив, если данных нет). */
  const getDistrictTasks = computed((): Task[] => {
    if (!districtData.value) return []
    return districtData.value.dataset.tasks
  })

  /** Список инженеров района (пустой массив, если данных нет). */
  const getDistrictEngineers = computed((): Engineer[] => {
    if (!districtData.value) return []
    return districtData.value.dataset.engineers
  })

  /** Список инженеров в формате `{ title, value }` для UI-селекторов. */
  const getDistrictEngineersSelector = computed(() =>
    getDistrictEngineers.value.map((item) => ({
      title: item.name,
      value: item.id,
    })),
  )

  /** Маршруты инженеров из результата оптимизации. */
  const getRoutes = computed((): EngineerRoute[] => {
    if (!districtData.value) return []
    if (!districtData.value.result) return []
    return districtData.value.result.routes
  })

  /** Дистанция по каждому инженеру (id → км). */
  const getDistanceByEngineer = computed((): Record<string, number> => {
    if (!districtData.value) return {}
    if (!districtData.value.result) return {}
    return districtData.value.result.distance_by_engineer
  })

  /** Агрегированные метрики оптимизации. */
  const getMetrics = computed((): OptimizationMetrics | null => {
    if (!districtData.value) return null
    if (!districtData.value.result) return null
    return districtData.value.result.metrics
  })

  /** Время в пути по каждому инженеру (id → минуты). */
  const getTravelTimeByEngineer = computed((): Record<string, number> => {
    if (!districtData.value) return {}
    if (!districtData.value.result) return {}
    return districtData.value.result.travel_time_by_engineer
  })

  /** Задачи, которые не удалось назначить. */
  const getUnassigned = computed((): UnassignedTask[] => {
    if (!districtData.value) return []
    if (!districtData.value.result) return []
    return districtData.value.result.unassigned
  })

  // --- Загрузка данных района --------------------------------------------

  /**
   * Загружает данные района по текущему `districtCode`.
   * При успехе обновляет `districtData` и синхронизирует `currentConsiderEquipment`.
   */
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

  // --- Сброс датасетов ----------------------------------------------------

  /** Флаг выполнения полного сброса датасетов. */
  const loadingResetAllDatasets = ref<boolean>(false)

  /**
   * Выполняет полный сброс датасетов к официальному набору.
   * Результат запроса намеренно игнорируется.
   */
  const resetAllDatasets = async () => {
    loadingResetAllDatasets.value = true
    await sendRequest(baseUrls.RESET_ALL)
    loadingResetAllDatasets.value = false
  }

  // --- Оптимизация --------------------------------------------------------

  /** Флаг выполнения оптимизации. */
  const loadingOptimization = ref<boolean>(false)

  /**
   * Запускает оптимизацию маршрутов для текущего района.
   * При успехе обновляет `districtData` и синхронизирует `currentConsiderEquipment`.
   *
   * @param data Параметры запроса оптимизации.
   */
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

  // --- Выбор территории и маршрутов --------------------------------------

  /**
   * Устанавливает код текущей территории.
   * Загрузка данных выполняется автоматически через `watch`.
   *
   * @param code Код территории.
   */
  const selectDistrict = (code: string) => {
    districtCode.value = code
  }

  /**
   * Переключает выделение маршрута инженера.
   *
   * @param engineerId Идентификатор инженера.
   */
  const toggleRouteSelection = (engineerId: string) => {
    const i = selectedRoutes.value.indexOf(engineerId)
    if (i === -1) selectedRoutes.value.push(engineerId)
    else selectedRoutes.value.splice(i, 1)
  }

  /**
   * Проверяет, выделен ли маршрут инженера.
   *
   * @param engineerId Идентификатор инженера.
   * @returns `true`, если маршрут выделен.
   */
  const isRouteSelected = (engineerId: string) => selectedRoutes.value.includes(engineerId)

  /** Сбрасывает выделение всех маршрутов. */
  const clearRouteSelection = () => {
    selectedRoutes.value = []
  }

  /**
   * Автоматически загружает данные района при смене `districtCode`.
   * `nextTick` даёт возможность реактивным зависимостям обновиться до запроса.
   */
  watch(districtCode, async (nVal) => {
    if (!nVal) return
    await nextTick()
    await loadDistrictData()
  })

  // --- Пояснение к остановке маршрута ------------------------------------

  /** Флаг загрузки пояснения. */
  const loadingExplanation = ref<boolean>(false)
  /** Идентификатор задачи, для которой загружается пояснение. */
  const explanationTaskId = ref<string>('')
  /** Текущее пояснение к остановке. */
  const taskExplanation = ref<RouteStopExplanationObject | null>(null)

  /**
   * Загружает пояснение к остановке маршрута для указанной задачи.
   *
   * Если пояснение для этой задачи уже загружено — ничего не делает.
   * Защищается от гонок: ответ применяется только если `taskId`
   * совпадает с актуальным `explanationTaskId`.
   *
   * @param taskId Идентификатор задачи.
   */
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

  // --- Ручное переназначение ---------------------------------------------

  /** Флаг загрузки превью переназначения. */
  const loadingManualReassignmentPreview = ref<boolean>(false)
  /** Результат превью переназначения (успешный или ошибочный). */
  const manualReassignmentObject = ref<PreviewReassignmentObject | null>(null)

  /** Очищает результат превью переназначения. */
  const clearManualReassignmentPreview = () => {
    manualReassignmentObject.value = null
  }

  /**
   * Загружает превью ручного переназначения задачи.
   * Ошибочный ответ API нормализуется в `PreviewReassignmentObject`.
   *
   * @param data Параметры запроса превью.
   */
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

  /** Флаг подтверждения переназначения. */
  const loadingManualReassignment = ref<boolean>(false)

  /**
   * Подтверждает ручное переназначение по текущему превью.
   * Ничего не делает, если превью отсутствует или недопустимо (`feasible === false`).
   * При успехе обновляет `districtData` и сбрасывает выделение маршрутов.
   */
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

  // --- Перепланирование ---------------------------------------------------

  /** Флаг перепланирования. */
  const loadingReplan = ref<boolean>(false)

  /**
   * Запускает перепланирование по событию (инженер недоступен,
   * отмена задачи, экстренная задача).
   *
   * @param data Данные события перепланирования.
   */
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

  // --- Создание задачи ----------------------------------------------------

  /** Флаг создания задачи. */
  const loadingCreateTask = ref<boolean>(false)

  /**
   * Создаёт задачу в текущем районе.
   * При успехе обновляет `districtData`.
   *
   * @param data Данные новой задачи.
   */
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

  // --- Обновление статуса задачи -----------------------------------------

  /** Флаг обновления статуса задачи. */
  const loadingUpdateTaskStatus = ref<boolean>(false)

  /**
   * Обновляет статус задачи.
   * При успехе обновляет `districtData` и сбрасывает выделение маршрутов.
   *
   * @param data Данные для обновления статуса.
   */
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
