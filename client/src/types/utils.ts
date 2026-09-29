/**
 * Базовые доменные типы (union-типы), производные от справочников-констант.
 *
 * Каждый тип представляет собой объединение ключей соответствующей map-константы
 * из `@/utils/consts.ts`, что обеспечивает единый источник истины между
 * runtime-справочниками и типами.
 *
 * Модуль содержит только декларации типов и не имеет runtime-кода.
 */

import {
  PRIORITY_TYPE_MAP,
  SKILL_TYPE_MAP,
  TASK_STATUS_MAP,
  VEHICLE_TYPE_MAP,
  WORK_TYPE_MAP,
} from '@/utils/consts.ts'

/** Тип транспортного средства (ключи `VEHICLE_TYPE_MAP`). */
export type VehicleType = keyof typeof VEHICLE_TYPE_MAP

/** Навык (квалификация) инженера (ключи `SKILL_TYPE_MAP`). */
export type SkillType = keyof typeof SKILL_TYPE_MAP

/** Приоритет задачи (ключи `PRIORITY_TYPE_MAP`). */
export type PriorityType = keyof typeof PRIORITY_TYPE_MAP

/** Тип работ (ключи `WORK_TYPE_MAP`). */
export type WorkType = keyof typeof WORK_TYPE_MAP

/** Статус задачи (ключи `TASK_STATUS_MAP`). */
export type TaskStatus = keyof typeof TASK_STATUS_MAP
