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
