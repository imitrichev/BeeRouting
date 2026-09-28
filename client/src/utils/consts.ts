import type { TaskStatus } from '@/types/utils.ts'

export const API_URL = String(import.meta.env.VITE_API_URL)

export enum HTTP_METHODS {
  GET = 'GET',
  POST = 'POST',
  PUT = 'PUT',
  PATCH = 'PATCH',
  DELETE = 'DELETE',
  OPTIONS = 'OPTIONS',
  HEAD = 'HEAD',
}

export const VEHICLE_TYPE_MAP = {
  CAR: 'Автомобиль',
  PUBLIC_TRANSPORT: 'Общ. транспорт',
  WALK: 'Пешком',
  BICYCLE: 'Велосипед',
} as const

export const SKILL_TYPE_MAP = {
  LOCAL_WORKS: 'Локальные работы',
  EMERGENCY_WORKS: 'Аварийные работы',
  CONNECTION_AND_UPSELL: 'Подключение и дозаказы',
} as const

export const PRIORITY_TYPE_MAP = {
  URGENT: 'Срочный',
  NORMAL: 'Обычный',
} as const

export const WORK_TYPE_MAP = {
  CONNECTION: 'Подключение клиентов',
  EMERGENCY: 'Авария',
  EQUIPMENT_ORDER: 'Дозаказ оборудования',
  LOCAL: 'Локальная заявка / ремонт',
} as const

export const TASK_STATUS_MAP = {
  NOT_SENT: 'не отправлена',
  ASSIGNED: 'назначена',
  EN_ROUTE: 'в пути',
  IN_PROGRESS: 'в работе',
  COMPLETED: 'выполнена',
  CANCELLED: 'отменена',
  OVERDUE: 'просрочена',
} as const

export const TASK_STATUS_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  NOT_SENT: [],
  ASSIGNED: ['EN_ROUTE', 'CANCELLED', 'NOT_SENT'],
  EN_ROUTE: ['IN_PROGRESS', 'CANCELLED', 'ASSIGNED'],
  IN_PROGRESS: ['COMPLETED', 'CANCELLED'],
  COMPLETED: [],
  CANCELLED: [],
  OVERDUE: ['EN_ROUTE', 'NOT_SENT', 'COMPLETED', 'CANCELLED'],
}
