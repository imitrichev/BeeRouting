export interface Engineer {
  id: string
  name: string
  qualifications: string[]
  vehicle_type: string
  start_location_id: string
  start_latitude: number | null
  start_longitude: number | null
  available_from: string
  available_until: string
}

export interface Task {
  id: string
  location_id: string
  latitude: number | null
  longitude: number | null
  address: string | null
  required_skill: string
  duration_minutes: number
  window_start: string
  window_end: string
  priority: string
  required_vehicle_type: string | null
  required_equipment: string[]
  status: string
  current_engineer_id: string | null
  is_plannable: boolean
  assignment_locked: boolean
}

export interface Dataset {
  source_name: string | null
  scenario_name: string
  engineers: Engineer[]
  tasks: Task[]
}

export interface RouteStop {
  task_id: string
  latitude: number | null
  longitude: number | null
  arrival_time: string
  service_start_time: string
  service_end_time: string
  travel_time_from_previous: number
  distance_from_previous_km: number
}

export interface EngineerRoute {
  engineer_id: string
  engineer_name: string
  vehicle_type: string
  start_latitude: number | null
  start_longitude: number | null
  total_distance_km: number
  total_travel_minutes: number
  geometry: {
    type: string
    coordinates: number[][]
  } | null
  stops: RouteStop[]
}

export interface Metrics {
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

export interface UnassignedTask {
  task_id: string
  reason_code: string
  message: string
}

export interface OptimizationResult {
  metrics: Metrics
  distance_by_engineer: Record<string, number>
  travel_time_by_engineer: Record<string, number>
  routes: EngineerRoute[]
  unassigned: UnassignedTask[]
}

export interface ExplanationResponse {
  task_id: string
  decision_trace?: Record<string, unknown>
  explanation: string
  developer_mode: boolean
}

export interface ApiResponse {
  dataset: Dataset
  result?: OptimizationResult
}

export interface ReassignmentMetrics {
  used_engineers_count: number
  total_distance_km: number
}

export interface ManualReassignmentPreview {
  feasible: boolean
  proposal_id?: string
  task_id?: string
  reason_code?: string
  message?: string
  old_engineer?: { id: string; name: string } | null
  new_engineer?: { id: string; name: string }
  before?: ReassignmentMetrics
  after?: ReassignmentMetrics
  delta?: ReassignmentMetrics
}
