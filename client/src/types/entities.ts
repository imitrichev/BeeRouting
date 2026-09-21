export type Engineer = {
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

export type Task = {
  id: string
  location_id: string
  latitude: number | null
  longitude: number | null
  required_skill: string
  duration_minutes: number
  window_start: string
  window_end: string
  priority: string
  required_vehicle_type: string | null
}

export type Dataset = {
  source_name: string | null
  scenario_name: string
  engineers: Engineer[]
  tasks: Task[]
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

export type Metrics = {
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
}

export type UnassignedTask = {
  task_id: string
  reason_code: string
  message: string
}

export type OptimizationResult = {
  metrics: Metrics
  distance_by_engineer: Record<string, number>
  travel_time_by_engineer: Record<string, number>
  routes: EngineerRoute[]
  unassigned: UnassignedTask[]
}

export type DefaultDatasetApiResponse = {
  dataset: Dataset
}

export type OptimizeApiResponse = {
  dataset: Dataset
  result: OptimizationResult
}
