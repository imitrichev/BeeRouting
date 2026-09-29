/**
 * Общие константы приложения: базовый URL API, HTTP-методы и справочники
 * предметной области (типы транспорта, навыки, приоритеты, типы работ,
 * статусы задач и допустимые переходы между ними).
 *
 * Справочники объявлены через `as const`, что позволяет выводить из них
 * union-типы (`keyof typeof MAP`) в `@/types/utils.ts`.
 */

import type { TaskStatus } from '@/types/utils.ts'

/** Базовый URL API, берётся из переменной окружения `VITE_API_URL`. */
export const API_URL = String(import.meta.env.VITE_API_URL)

/**
 * Поддерживаемые HTTP-методы.
 */
export enum HTTP_METHODS {
  GET = 'GET',
  POST = 'POST',
  PUT = 'PUT',
  PATCH = 'PATCH',
  DELETE = 'DELETE',
  OPTIONS = 'OPTIONS',
  HEAD = 'HEAD',
}

/**
 * Справочник типов транспортных средств: код → подпись.
 */
export const VEHICLE_TYPE_MAP = {
  CAR: 'Автомобиль',
  PUBLIC_TRANSPORT: 'Общ. транспорт',
  WALK: 'Пешком',
  BICYCLE: 'Велосипед',
} as const

/**
 * Справочник навыков (квалификаций) инженеров: код → подпись.
 */
export const SKILL_TYPE_MAP = {
  LOCAL_WORKS: 'Локальные работы',
  EMERGENCY_WORKS: 'Аварийные работы',
  CONNECTION_AND_UPSELL: 'Подключение и дозаказы',
} as const

/**
 * Справочник приоритетов задач: код → подпись.
 */
export const PRIORITY_TYPE_MAP = {
  URGENT: 'Срочный',
  NORMAL: 'Обычный',
} as const

/**
 * Справочник типов работ: код → подпись.
 */
export const WORK_TYPE_MAP = {
  CONNECTION: 'Подключение клиентов',
  EMERGENCY: 'Авария',
  EQUIPMENT_ORDER: 'Дозаказ оборудования',
  LOCAL: 'Локальная заявка / ремонт',
} as const

/**
 * Справочник статусов задач: код → подпись.
 */
export const TASK_STATUS_MAP = {
  NOT_SENT: 'не назначена',
  ASSIGNED: 'назначена',
  EN_ROUTE: 'в пути',
  IN_PROGRESS: 'в работе',
  COMPLETED: 'выполнена',
  CANCELLED: 'отменена',
  OVERDUE: 'просрочена',
} as const

/**
 * Допустимые переходы между статусами задачи.
 *
 * Ключ — текущий статус, значение — массив статусов, в которые разрешён переход.
 * Пустой массив означает терминальный статус. Используется утилитами из `@/utils/task.ts`.
 */
export const TASK_STATUS_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  NOT_SENT: [],
  ASSIGNED: ['EN_ROUTE', 'CANCELLED', 'NOT_SENT'],
  EN_ROUTE: ['IN_PROGRESS', 'CANCELLED', 'ASSIGNED'],
  IN_PROGRESS: ['COMPLETED', 'CANCELLED'],
  COMPLETED: [],
  CANCELLED: [],
  OVERDUE: ['EN_ROUTE', 'NOT_SENT', 'COMPLETED', 'CANCELLED'],
}
