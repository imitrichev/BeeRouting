import type { PriorityType, SkillType, TaskStatus, VehicleType, WorkType } from '@/types/utils.ts'

export type Engineer = {
  id: string
  name: string
  qualifications: SkillType[]
  vehicle_type: VehicleType
  start_location_id: string
  start_address: string | null
  start_latitude: number | null
  start_longitude: number | null
  available_from: string
  available_until: string
  available_router_count: number
}

export type Task = {
  id: string
  location_id: string
  latitude: number | null
  longitude: number | null
  address: string | null
  required_skill: SkillType
  duration_minutes: number
  window_start: string
  window_end: string
  priority: PriorityType
  required_vehicle_type: string | null
  required_equipment: string[]
  required_router_count: number
  status: string
  current_engineer_id: string | null
  is_plannable: boolean
  assignment_locked: boolean
}

export type DistrictDataDataset = {
  source_name: string
  scenario_name: string
  office_address: string | null
  office_latitude: number | null
  office_longitude: number | null
  engineers: Engineer[]
  tasks: Task[]
}

export type OptimizationMetrics = {
  assigned_task_count: number
  unassigned_task_count: number
  used_engineers_count: number
  total_distance_km: number
  total_travel_minutes: number
  total_objective: number
  unassigned_penalty: number
  used_engineers_penalty: number
  distance_penalty: number
  travel_time_penalty: number
  plan_disruption_penalty: number
  reassigned_task_count: number
  reordered_task_count: number
}

export type UnassignedTask = {
  task_id: string
  reason_code: string
  message: string
}

export type RouteStop = {
  task_id: string
  latitude: number | null
  longitude: number | null
  arrival_time: string
  service_start_time: string
  service_end_time: string
  travel_time_from_previous: number
  distance_from_previous_km: number
}

export type EngineerRoute = {
  engineer_id: string
  engineer_name: string
  vehicle_type: string
  start_latitude: number
  start_longitude: number
  total_distance_km: number
  total_travel_minutes: number
  geometry: {
    type: string
    coordinates: number[][]
  } | null
  stops: RouteStop[]
}

export type DistrictDataOptimizationResult = {
  metrics: OptimizationMetrics
  distance_by_engineer: Record<string, number>
  travel_time_by_engineer: Record<string, number>
  routes: EngineerRoute[]
  unassigned: UnassignedTask[]
}

export type DistrictData = {
  territory_code: string
  planning_options: {
    consider_equipment: boolean
    preserve_assigned_tasks: boolean
    ignore_task_statuses: boolean
    planning_time: string | null
  }
  dataset: DistrictDataDataset
  result?: DistrictDataOptimizationResult
}

export type RouteStopExplanationObject = {
  explanation: string
  task_id: string
}

export type OptimizationRequestData = {
  consider_equipment: boolean
  ignore_task_statuses: true
  planning_time: null
  solver: 'baseline' | 'ortools'
}

export type PreviewReassignmentObjectEngineer = {
  id: string
  name: string
}
export type PreviewReassignmentObjectMetrics = {
  used_engineers_count: number
  total_distance_km: number
}

export type SuccessPreviewReassignmentObject = {
  feasible: true
  proposal_id: string
  task_id: string
  old_engineer: PreviewReassignmentObjectEngineer
  new_engineer: PreviewReassignmentObjectEngineer
  before: PreviewReassignmentObjectMetrics
  after: PreviewReassignmentObjectMetrics
  delta: PreviewReassignmentObjectMetrics
}

export type PreviewReassignmentRequestData = {
  engineer_id: string
  task_id: string
}

export type ErrorPreviewReassignmentObject = {
  feasible: false
  reason_code: string
  message: string
}

export type PreviewReassignmentObject =
  ErrorPreviewReassignmentObject | SuccessPreviewReassignmentObject

export type ReplanEventType = 'ENGINEER_UNAVAILABLE' | 'TASK_CANCELLED' | 'EMERGENCY_TASK'

export interface EngineerUnavailableReplanRequestData {
  event_type: 'ENGINEER_UNAVAILABLE'
  consider_equipment: boolean
  engineer_id: string
}

export interface TaskCancelledReplanRequestData {
  event_type: 'TASK_CANCELLED'
  consider_equipment: boolean
  task_id: string
}

export interface EmergencyTaskReplanRequestData {
  event_type: 'EMERGENCY_TASK'
  consider_equipment: boolean
  task: {
    id: string
    latitude: number
    longitude: number
    work_type: WorkType
    window_start: string
    window_end: string
    required_vehicle_type: string | null
    required_router_count: number
  }
}

export type ReplanRequestData =
  | EngineerUnavailableReplanRequestData
  | TaskCancelledReplanRequestData
  | EmergencyTaskReplanRequestData

export type TaskCreateRequestData = {
  id: string
  address: string
  latitude: number
  longitude: number
  work_type: WorkType
  window_start: string
  window_end: string
  required_vehicle_type: string | null
  required_router_count: number
}

export type TaskStatusUpdateRequestData = {
  task_id: string
  status: TaskStatus
}
