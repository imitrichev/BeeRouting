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

const createReplacer = <T extends Record<string, string>>(map: T) => {
  const keys = Object.keys(map)
  if (keys.length === 0) {
    return (message: string) => message
  }

  const escaped = keys
    .sort((a, b) => b.length - a.length)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')

  const pattern = new RegExp(`\\b(${escaped})\\b`, 'g')

  return (message: string): string => {
    if (!message) return message
    return message.replace(pattern, (match) => `"${map[match as keyof T] ?? match}"`)
  }
}

export const replaceSkillTypes = createReplacer(SKILL_TYPE_MAP)
export const replacePriorityTypes = createReplacer(PRIORITY_TYPE_MAP)
export const replaceVehicleTypes = createReplacer(VEHICLE_TYPE_MAP)

export const getWordDeclension = (
  number: number,
  one: string,
  two: string,
  five: string,
): string => {
  let n = Math.abs(number % 100)
  if (n >= 5 && n <= 20) return five
  n %= 10
  if (n === 1) return one
  if (n >= 2 && n <= 4) return two
  return five
}
