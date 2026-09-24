import { PRIORITY_TYPE_MAP, SKILL_TYPE_MAP, VEHICLE_TYPE_MAP } from '@/utils/consts.ts'
import type { PriorityType, SkillType, VehicleType } from '@/types/utils.ts'

export const getVehicleTypeTranslation = (type: string | null): string => {
  if (!type) return '-'
  if (!Object.keys(VEHICLE_TYPE_MAP).includes(type)) return 'Неизвестно'
  return VEHICLE_TYPE_MAP[type as VehicleType]
}

export const getSkillTranslation = (type: string): string => {
  if (!type) return '-'
  if (!Object.keys(SKILL_TYPE_MAP).includes(type)) return 'Неизвестно'
  return SKILL_TYPE_MAP[type as SkillType]
}

export const getPriorityTranslation = (type: string): string => {
  if (!type) return '-'
  if (!Object.keys(PRIORITY_TYPE_MAP).includes(type)) return 'Неизвестно'
  return PRIORITY_TYPE_MAP[type as PriorityType]
}
