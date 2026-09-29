/**
 * Утилиты для работы со статусами задач: проверка терминальных состояний,
 * допустимых переходов, а также вспомогательные функции для маршрутов
 * и отображения статусов в UI.
 *
 * Источник истины по статусам и переходам — константы из `@/utils/consts.ts`.
 */

import type { TaskStatus } from '@/types/utils.ts'
import { TASK_STATUS_MAP, TASK_STATUS_TRANSITIONS } from '@/utils/consts.ts'
import type { EngineerRoute, Task } from '@/types/entities.ts'

/**
 * Проверяет, является ли статус терминальным (без допустимых переходов).
 *
 * @param status Статус задачи.
 * @returns `true`, если из статуса нельзя перейти ни в один другой.
 */
export const isTerminalStatus = (status: TaskStatus): boolean =>
  TASK_STATUS_TRANSITIONS[status].length === 0

/**
 * Проверяет, допустим ли переход из одного статуса в другой.
 *
 * @param from Исходный статус.
 * @param to   Целевой статус.
 * @returns `true`, если переход разрешён.
 */
export const canTransition = (from: TaskStatus, to: TaskStatus): boolean =>
  TASK_STATUS_TRANSITIONS[from].includes(to)

/**
 * Возвращает список статусов, в которые можно перейти из указанного.
 *
 * @param from Исходный статус.
 * @returns Массив допустимых целевых статусов.
 */
export const getAvailableTransitions = (from: TaskStatus): TaskStatus[] =>
  TASK_STATUS_TRANSITIONS[from]

/**
 * Статусы, обозначающие завершение работы над задачей (успешное или отмену).
 */
export const TERMINAL_DONE_STATUSES: TaskStatus[] = ['COMPLETED', 'CANCELLED']

/**
 * Проверяет, относится ли статус к «завершённым» (COMPLETED или CANCELLED).
 *
 * @param status Статус задачи.
 * @returns `true`, если задача завершена или отменена.
 */
export const isDoneStatus = (status: TaskStatus): boolean => TERMINAL_DONE_STATUSES.includes(status)

/**
 * Проверяет, что все остановки маршрута, предшествующие указанной задаче,
 * находятся в завершённом статусе (COMPLETED или CANCELLED).
 *
 * Задачи, отсутствующие в `tasksById`, пропускаются (не влияют на результат).
 * Если задача — первая в маршруте или не найдена, возвращается `true`.
 *
 * @param route     Маршрут инженера.
 * @param taskId    Идентификатор целевой задачи.
 * @param tasksById Карта задач по идентификатору.
 * @returns `true`, если все предыдущие остановки завершены (или их нет).
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
 * Находит маршрут, содержащий указанную задачу.
 *
 * @param routes Список маршрутов инженеров.
 * @param taskId Идентификатор задачи.
 * @returns Маршрут, содержащий задачу, либо `null`, если задача не найдена.
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

/**
 * Возвращает человекочитаемую метку статуса задачи.
 *
 * @param status Статус (может быть `null`/`undefined`).
 * @returns Метка из `TASK_STATUS_MAP`, исходная строка, если метка не найдена,
 *          или `'-'` для пустого значения.
 */
export const getTaskStatusLabel = (status: string | null | undefined): string => {
  if (!status) return '-'
  return TASK_STATUS_MAP[status as TaskStatus] ?? status
}

/**
 * Возвращает цвет (токен Vuetify) для отображения статуса задачи.
 *
 * @param status Статус (может быть `null`/`undefined`).
 * @returns Название цветового токена либо `'grey'`, если статус неизвестен.
 */
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

/**
 * Проверяет, отменена ли задача.
 * Для отменённых задач действия недоступны.
 *
 * @param status Статус задачи (может быть `null`/`undefined`).
 * @returns `true`, если задача отменена.
 */
export const isCancelledStatus = (status: string | null | undefined): boolean => {
  return status === 'CANCELLED'
}
