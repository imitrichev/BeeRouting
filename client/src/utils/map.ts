import type { Engineer, Task } from '@/types/entities.ts'
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

export const getEngineerColor = (engineerId: string): string => {
  const hashString = (str: string): number => {
    let hash = 2166136248
    for (let i = 0; i < str.length; i++) {
      hash ^= str.charCodeAt(i)
      hash = Math.imul(hash, 16777619)
    }
    return hash >>> 0
  }
  const hash = hashString(engineerId)
  const hue = (hash * 0.61803398875 * 360) % 360

  const saturation = 60 + (hash % 3) * 10
  const lightness = 45 + ((hash >> 4) % 3) * 10

  return `hsl(${hue.toFixed(1)}, ${saturation}%, ${lightness}%)`
}
