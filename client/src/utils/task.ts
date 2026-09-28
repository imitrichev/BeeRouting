import type { TaskStatus } from '@/types/utils.ts'
import { TASK_STATUS_MAP, TASK_STATUS_TRANSITIONS } from '@/utils/consts.ts'
import type { EngineerRoute, Task } from '@/types/entities.ts'

export const isTerminalStatus = (status: TaskStatus): boolean =>
  TASK_STATUS_TRANSITIONS[status].length === 0

export const canTransition = (from: TaskStatus, to: TaskStatus): boolean =>
  TASK_STATUS_TRANSITIONS[from].includes(to)

export const getAvailableTransitions = (from: TaskStatus): TaskStatus[] =>
  TASK_STATUS_TRANSITIONS[from]

export const TERMINAL_DONE_STATUSES: TaskStatus[] = ['COMPLETED', 'CANCELLED']

export const isDoneStatus = (status: TaskStatus): boolean => TERMINAL_DONE_STATUSES.includes(status)

/**
 * Возвращает true, если все заявки маршрута, идущие ДО указанной,
 * находятся в COMPLETED или CANCELLED.
 */
export const arePreviousStopsDone = (
  route: EngineerRoute,
  taskId: string,
  tasksById: Map<string, Task>,
): boolean => {
  const idx = route.stops.findIndex((s) => s.task_id === taskId)
  if (idx <= 0) return true
  for (let i = 0; i < idx; i++) {
    const prev = route.stops[i]
    const prevTask = prev ? tasksById.get(prev.task_id) : undefined
    if (!prevTask) continue
    if (!isDoneStatus(prevTask.status as TaskStatus)) return false
  }
  return true
}

/**
 * Есть ли задача вообще в каком-либо маршруте.
 */
export const findRouteByTaskId = (
  routes: EngineerRoute[],
  taskId: string,
): EngineerRoute | null => {
  for (const route of routes) {
    if (route.stops.some((s) => s.task_id === taskId)) return route
  }
  return null
}

export const getTaskStatusLabel = (status: string | null | undefined): string => {
  if (!status) return '-'
  return TASK_STATUS_MAP[status as TaskStatus] ?? status
}

export const getTaskStatusColor = (status: string | null | undefined): string => {
  if (!status) return 'grey'
  return (
    {
      NOT_SENT: 'grey',
      ASSIGNED: 'indigo',
      EN_ROUTE: 'cyan-darken-1',
      IN_PROGRESS: 'blue-darken-1',
      COMPLETED: 'success',
      CANCELLED: 'grey-darken-1',
      OVERDUE: 'error',
    }[status] ?? 'grey'
  )
}
