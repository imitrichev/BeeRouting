/**
 * Утилиты локализации и форматирования для доменных справочников:
 * перевод кодов (тип транспорта, навык, приоритет, тип работ) в человекочитаемые
 * подписи, замена кодов на подписи внутри текстовых сообщений и склонение
 * существительных по числу в русском языке.
 */

import {
  PRIORITY_TYPE_MAP,
  SKILL_TYPE_MAP,
  VEHICLE_TYPE_MAP,
  WORK_TYPE_MAP,
} from '@/utils/consts.ts'
import type { PriorityType, SkillType, VehicleType, WorkType } from '@/types/utils.ts'

/**
 * Возвращает человекочитаемую подпись для типа транспортного средства.
 *
 * @param type Код типа транспорта (может быть `null`).
 * @returns Подпись, `'-'` для пустого значения или `'Неизвестно'` для неизвестного кода.
 */
export const getVehicleTypeTranslation = (type: string | null): string => {
  if (!type) return '-'
  if (!Object.keys(VEHICLE_TYPE_MAP).includes(type)) return 'Неизвестно'
  return VEHICLE_TYPE_MAP[type as VehicleType]
}

/**
 * Возвращает человекочитаемую подпись для навыка.
 *
 * @param type Код навыка.
 * @returns Подпись, `'-'` для пустого значения или `'Неизвестно'` для неизвестного кода.
 */
export const getSkillTranslation = (type: string): string => {
  if (!type) return '-'
  if (!Object.keys(SKILL_TYPE_MAP).includes(type)) return 'Неизвестно'
  return SKILL_TYPE_MAP[type as SkillType]
}

/**
 * Возвращает человекочитаемую подпись для приоритета.
 *
 * @param type Код приоритета.
 * @returns Подпись, `'-'` для пустого значения или `'Неизвестно'` для неизвестного кода.
 */
export const getPriorityTranslation = (type: string): string => {
  if (!type) return '-'
  if (!Object.keys(PRIORITY_TYPE_MAP).includes(type)) return 'Неизвестно'
  return PRIORITY_TYPE_MAP[type as PriorityType]
}

/**
 * Возвращает человекочитаемую подпись для типа работ.
 *
 * @param type Код типа работ.
 * @returns Подпись, `'-'` для пустого значения или `'Неизвестно'` для неизвестного кода.
 */
export const getWorkTypeTranslation = (type: string): string => {
  if (!type) return '-'
  if (!Object.keys(WORK_TYPE_MAP).includes(type)) return 'Неизвестно'
  return WORK_TYPE_MAP[type as WorkType]
}

/**
 * Создаёт функцию, которая заменяет в тексте коды справочника на их подписи,
 * оборачивая подписи в двойные кавычки.
 *
 * Заменяются только целые слова (по границам `\b`). Ключи сортируются по убыванию
 * длины, чтобы более длинные коды не перекрывались короткими. Спецсимволы
 * регулярного выражения в ключах экранируются.
 *
 * @template T Тип map-справочника (код → подпись).
 * @param map Справочник для замены.
 * @returns Функция-заменитель. Если справочник пуст — возвращает исходную строку без изменений.
 */
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

/** Заменяет в тексте коды навыков на их подписи (в кавычках). */
export const replaceSkillTypes = createReplacer(SKILL_TYPE_MAP)

/** Заменяет в тексте коды приоритетов на их подписи (в кавычках). */
export const replacePriorityTypes = createReplacer(PRIORITY_TYPE_MAP)

/** Заменяет в тексте коды типов транспорта на их подписи (в кавычках). */
export const replaceVehicleTypes = createReplacer(VEHICLE_TYPE_MAP)

/** Заменяет в тексте коды типов работ на их подписи (в кавычках). */
export const replaceWorkTypes = createReplacer(WORK_TYPE_MAP)

/**
 * Возвращает правильную форму существительного для заданного числа
 * по правилам русского языка.
 *
 * @param number Число, с которым согласуется существительное.
 * @param one    Форма для 1, 21, 31, … (например, `'задача'`).
 * @param two    Форма для 2–4, 22–24, … (например, `'задачи'`).
 * @param five   Форма для 0, 5–20, 25–30, … (например, `'задач'`).
 * @returns Одна из переданных форм.
 *
 * @example
 * getWordDeclension(1, 'задача', 'задачи', 'задач')  // 'задача'
 * getWordDeclension(3, 'задача', 'задачи', 'задач')  // 'задачи'
 * getWordDeclension(5, 'задача', 'задачи', 'задач')  // 'задач'
 */
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
