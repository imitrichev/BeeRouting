import type { Task } from '@/types/entities.ts'
import type { Feature, FeatureCollection, Point } from 'geojson'

export type TaskFeatureProperties = {
  id: string
  required_skill: string
  priority: string
  duration_minutes: number
  window_start: string
  window_end: string
  location_id: string
  required_vehicle_type: string | null
}

export const tasksToFeatureCollection = (
  tasks: Task[],
): FeatureCollection<Point, TaskFeatureProperties> => {
  const features: Feature<Point, TaskFeatureProperties>[] = tasks
    .filter((t) => t.latitude != null && t.longitude != null)
    .map((t) => ({
      type: 'Feature',
      id: t.id,
      geometry: {
        type: 'Point',
        coordinates: [t.longitude as number, t.latitude as number],
      },
      properties: {
        id: t.id,
        required_skill: t.required_skill,
        priority: t.priority,
        duration_minutes: t.duration_minutes,
        window_start: t.window_start,
        window_end: t.window_end,
        location_id: t.location_id,
        required_vehicle_type: t.required_vehicle_type,
      },
    }))

  return { type: 'FeatureCollection', features }
}
