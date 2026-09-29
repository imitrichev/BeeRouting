/**
 * Типы данных предметной области: инженеры, задачи, результаты оптимизации маршрутов,
 * а также структуры запросов/ответов API для планирования, перепланирования и превью-операций.
 *
 * Модуль содержит только декларации типов и не имеет runtime-кода.
 */

import type { PriorityType, SkillType, TaskStatus, VehicleType, WorkType } from '@/types/utils.ts'

/**
 * Инженер (исполнитель), доступный для назначения задач.
 */
export type Engineer = {
  /** Уникальный идентификатор инженера. */
  id: string
  /** Отображаемое имя. */
  name: string
  /** Список квалификаций (навыков), которыми владеет инженер. */
  qualifications: SkillType[]
  /** Тип транспортного средства, закреплённого за инженером. */
  vehicle_type: VehicleType
  /** Идентификатор стартовой локации. */
  start_location_id: string
  /** Адрес старта (может отсутствовать). */
  start_address: string | null
  /** Широта стартовой точки (может отсутствовать). */
  start_latitude: number | null
  /** Долгота стартовой точки (может отсутствовать). */
  start_longitude: number | null
  /** Время, с которого инженер доступен (ISO 8601). */
  available_from: string
  /** Время, до которого инженер доступен (ISO 8601). */
  available_until: string
  /** Количество роутеров, доступных инженеру. */
  available_router_count: number
  /** Признак активности инженера в текущем сценарии. */
  is_active: boolean
}

/**
 * Задача, подлежащая выполнению инженером.
 */
export type Task = {
  /** Уникальный идентификатор задачи. */
  id: string
  /** Идентификатор локации. */
  location_id: string
  /** Широта точки выполнения (может отсутствовать). */
  latitude: number | null
  /** Долгота точки выполнения (может отсутствовать). */
  longitude: number | null
  /** Адрес точки выполнения (может отсутствовать). */
  address: string | null
  /** Требуемый навык для выполнения задачи. */
  required_skill: SkillType
  /** Длительность выполнения в минутах. */
  duration_minutes: number
  /** Начало временного окна выполнения (ISO 8601). */
  window_start: string
  /** Конец временного окна выполнения (ISO 8601). */
  window_end: string
  /** Приоритет задачи. */
  priority: PriorityType
  /** Требуемый тип транспорта (если задан). */
  required_vehicle_type: string | null
  /** Список требуемого оборудования. */
  required_equipment: string[]
  /** Требуемое количество роутеров. */
  required_router_count: number
  /** Текущий статус задачи. */
  status: string
  /** Идентификатор инженера, назначенного на задачу (если есть). */
  current_engineer_id: string | null
  /** Признак того, что задача может быть включена в план. */
  is_plannable: boolean
  /** Признак блокировки переназначения задачи. */
  assignment_locked: boolean
}

/**
 * Набор исходных данных сценария: инженеры и задачи района.
 */
export type DistrictDataDataset = {
  /** Название источника данных. */
  source_name: string
  /** Название сценария. */
  scenario_name: string
  /** Адрес офиса (может отсутствовать). */
  office_address: string | null
  /** Широта офиса (может отсутствовать). */
  office_latitude: number | null
  /** Долгота офиса (может отсутствовать). */
  office_longitude: number | null
  /** Список инженеров. */
  engineers: Engineer[]
  /** Список задач. */
  tasks: Task[]
}

/**
 * Агрегированные метрики результата оптимизации.
 */
export type OptimizationMetrics = {
  /** Количество назначенных задач. */
  assigned_task_count: number
  /** Количество неназначенных задач. */
  unassigned_task_count: number
  /** Количество задействованных инженеров. */
  used_engineers_count: number
  /** Суммарная дистанция в километрах. */
  total_distance_km: number
  /** Суммарное время в пути в минутах. */
  total_travel_minutes: number
  /** Итоговое значение целевой функции. */
  total_objective: number
  /** Штраф за неназначенные задачи. */
  unassigned_penalty: number
  /** Штраф за использование инженеров. */
  used_engineers_penalty: number
  /** Штраф за дистанцию. */
  distance_penalty: number
  /** Штраф за время в пути. */
  travel_time_penalty: number
  /** Штраф за нарушение исходного плана. */
  plan_disruption_penalty: number
  /** Количество переназначенных задач. */
  reassigned_task_count: number
  /** Количество задач с изменённым порядком. */
  reordered_task_count: number
}

/**
 * Информация о задаче, которую не удалось назначить.
 */
export type UnassignedTask = {
  /** Идентификатор задачи. */
  task_id: string
  /** Код причины неназначения. */
  reason_code: string
  /** Человекочитаемое описание причины. */
  message: string
}

/**
 * Остановка (точка обслуживания) в маршруте инженера.
 */
export type RouteStop = {
  /** Идентификатор задачи, выполняемой на остановке. */
  task_id: string
  /** Широта точки (может отсутствовать). */
  latitude: number | null
  /** Долгота точки (может отсутствовать). */
  longitude: number | null
  /** Время прибытия (ISO 8601). */
  arrival_time: string
  /** Время начала обслуживания (ISO 8601). */
  service_start_time: string
  /** Время окончания обслуживания (ISO 8601). */
  service_end_time: string
  /** Время в пути от предыдущей остановки в минутах. */
  travel_time_from_previous: number
  /** Дистанция от предыдущей остановки в километрах. */
  distance_from_previous_km: number
}

/**
 * Маршрут инженера с последовательностью остановок и геометрией.
 */
export type EngineerRoute = {
  /** Идентификатор инженера. */
  engineer_id: string
  /** Имя инженера. */
  engineer_name: string
  /** Тип транспортного средства. */
  vehicle_type: string
  /** Широта стартовой точки маршрута. */
  start_latitude: number
  /** Долгота стартовой точки маршрута. */
  start_longitude: number
  /** Суммарная дистанция маршрута в километрах. */
  total_distance_km: number
  /** Суммарное время в пути в минутах. */
  total_travel_minutes: number
  /** GeoJSON-геометрия маршрута или null, если геометрия недоступна. */
  geometry: {
    /** Тип геометрии (например, "LineString"). */
    type: string
    /** Координаты в формате [долгота, широта]. */
    coordinates: number[][]
  } | null
  /** Список остановок маршрута. */
  stops: RouteStop[]
}

/**
 * Результат оптимизации по району: метрики, маршруты и неназначенные задачи.
 */
export type DistrictDataOptimizationResult = {
  /** Агрегированные метрики оптимизации. */
  metrics: OptimizationMetrics
  /** Дистанция по каждому инженеру (id → км). */
  distance_by_engineer: Record<string, number>
  /** Время в пути по каждому инженеру (id → минуты). */
  travel_time_by_engineer: Record<string, number>
  /** Построенные маршруты инженеров. */
  routes: EngineerRoute[]
  /** Задачи, которые не удалось назначить. */
  unassigned: UnassignedTask[]
}

/**
 * Данные района: параметры планирования, исходный датасет и, опционально, результат оптимизации.
 */
export type DistrictData = {
  /** Код территории. */
  territory_code: string
  /** Опции планирования. */
  planning_options: {
    /** Учитывать требуемое оборудование при назначении. */
    consider_equipment: boolean
    /** Сохранять уже назначенные задачи. */
    preserve_assigned_tasks: boolean
    /** Игнорировать статусы задач. */
    ignore_task_statuses: boolean
    /** Время планирования (ISO 8601) или null. */
    planning_time: string | null
  }
  /** Исходные данные сценария. */
  dataset: DistrictDataDataset
  /** Результат оптимизации (если расчёт выполнен). */
  result?: DistrictDataOptimizationResult
}

/**
 * Пояснение к остановке маршрута.
 */
export type RouteStopExplanationObject = {
  /** Текст пояснения. */
  explanation: string
  /** Идентификатор задачи. */
  task_id: string
}

/**
 * Данные запроса на оптимизацию.
 */
export type OptimizationRequestData = {
  /** Учитывать требуемое оборудование. */
  consider_equipment: boolean
  /** Учитывать рабочие статусы и сохранять существующие назначения. */
  ignore_task_statuses: false
  /** Время планирования всегда null (текущее время). */
  planning_time: null
  /** Используемый решатель. */
  solver: 'baseline' | 'ortools'
}

/**
 * Краткая информация об инженере в превью переназначения.
 */
export type PreviewReassignmentObjectEngineer = {
  /** Идентификатор инженера. */
  id: string
  /** Имя инженера. */
  name: string
}

/**
 * Метрики "до"/"после" в превью переназначения.
 */
export type PreviewReassignmentObjectMetrics = {
  /** Количество задействованных инженеров. */
  used_engineers_count: number
  /** Суммарная дистанция в километрах. */
  total_distance_km: number
}

/**
 * Успешный результат превью переназначения задачи.
 */
export type SuccessPreviewReassignmentObject = {
  /** Признак допустимости переназначения. */
  feasible: true
  /** Идентификатор предложения. */
  proposal_id: string
  /** Идентификатор задачи. */
  task_id: string
  /** Текущий инженер. */
  old_engineer: PreviewReassignmentObjectEngineer
  /** Предлагаемый инженер. */
  new_engineer: PreviewReassignmentObjectEngineer
  /** Метрики до переназначения. */
  before: PreviewReassignmentObjectMetrics
  /** Метрики после переназначения. */
  after: PreviewReassignmentObjectMetrics
  /** Разница метрик (after − before). */
  delta: PreviewReassignmentObjectMetrics
}

/**
 * Данные запроса на превью переназначения.
 */
export type PreviewReassignmentRequestData = {
  /** Идентификатор инженера. */
  engineer_id: string
  /** Идентификатор задачи. */
  task_id: string
}

/**
 * Ошибочный результат превью переназначения.
 */
export type ErrorPreviewReassignmentObject = {
  /** Признак недопустимости переназначения. */
  feasible: false
  /** Код причины. */
  reason_code: string
  /** Человекочитаемое описание причины. */
  message: string
}

/**
 * Результат превью переназначения: успешный или ошибочный.
 */
export type PreviewReassignmentObject =
  ErrorPreviewReassignmentObject | SuccessPreviewReassignmentObject

/**
 * Тип события перепланирования.
 */
export type ReplanEventType = 'ENGINEER_UNAVAILABLE' | 'TASK_CANCELLED' | 'EMERGENCY_TASK'

/**
 * Запрос на перепланирование из-за недоступности инженера.
 */
export interface EngineerUnavailableReplanRequestData {
  /** Тип события. */
  event_type: 'ENGINEER_UNAVAILABLE'
  /** Учитывать требуемое оборудование. */
  consider_equipment: boolean
  /** Идентификатор недоступного инженера. */
  engineer_id: string
}

/**
 * Запрос на перепланирование из-за отмены задачи.
 */
export interface TaskCancelledReplanRequestData {
  /** Тип события. */
  event_type: 'TASK_CANCELLED'
  /** Учитывать требуемое оборудование. */
  consider_equipment: boolean
  /** Идентификатор отменённой задачи. */
  task_id: string
}

/**
 * Запрос на перепланирование из-за экстренной задачи.
 */
export interface EmergencyTaskReplanRequestData {
  /** Тип события. */
  event_type: 'EMERGENCY_TASK'
  /** Учитывать требуемое оборудование. */
  consider_equipment: boolean
  /** Параметры экстренной задачи. */
  task: {
    /** Идентификатор задачи. */
    id: string
    /** Широта точки выполнения. */
    latitude: number
    /** Долгота точки выполнения. */
    longitude: number
    /** Тип работ. */
    work_type: WorkType
    /** Начало временного окна (ISO 8601). */
    window_start: string
    /** Конец временного окна (ISO 8601). */
    window_end: string
    /** Требуемый тип транспорта (если задан). */
    required_vehicle_type: string | null
    /** Требуемое количество роутеров. */
    required_router_count: number
  }
}

/**
 * Объединённый тип запроса на перепланирование.
 */
export type ReplanRequestData =
  | EngineerUnavailableReplanRequestData
  | TaskCancelledReplanRequestData
  | EmergencyTaskReplanRequestData

/**
 * Данные запроса на создание задачи.
 */
export type TaskCreateRequestData = {
  /** Идентификатор задачи. */
  id: string
  /** Адрес точки выполнения. */
  address: string
  /** Широта точки выполнения. */
  latitude: number
  /** Долгота точки выполнения. */
  longitude: number
  /** Тип работ. */
  work_type: WorkType
  /** Начало временного окна (ISO 8601). */
  window_start: string
  /** Конец временного окна (ISO 8601). */
  window_end: string
  /** Требуемый тип транспорта (если задан). */
  required_vehicle_type: string | null
  /** Требуемое количество роутеров. */
  required_router_count: number
}

/**
 * Данные запроса на обновление статуса задачи.
 */
export type TaskStatusUpdateRequestData = {
  /** Идентификатор задачи. */
  task_id: string
  /** Новый статус задачи. */
  status: TaskStatus
}
