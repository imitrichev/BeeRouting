import {
  PRIORITY_TYPE_MAP,
  SKILL_TYPE_MAP,
  VEHICLE_TYPE_MAP,
  WORK_TYPE_MAP,
} from '@/utils/consts.ts'

export type VehicleType = keyof typeof VEHICLE_TYPE_MAP
export type SkillType = keyof typeof SKILL_TYPE_MAP
export type PriorityType = keyof typeof PRIORITY_TYPE_MAP
export type WorkType = keyof typeof WORK_TYPE_MAP
