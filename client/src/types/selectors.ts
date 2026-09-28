/**
 * Типы элементов справочников (selectors) для выпадающих списков и фильтров:
 * территории, районы, приоритеты, навыки, нормы времени и типы транспорта.
 *
 * Модуль содержит только декларации типов и не имеет runtime-кода.
 */

/**
 * Элемент справочника территорий.
 */
export type TerritorySelectorItem = {
  /** Код территории. */
  code: string
  /** Название территории. */
  name: string
}

/**
 * Элемент справочника районов.
 */
export type DistrictSelectorItem = {
  /** Идентификатор района. */
  id: number
  /** Название района. */
  name: string
}

/**
 * Элемент справочника приоритетов.
 */
export type PrioritySelectorItem = {
  /** Код приоритета. */
  code: string
  /** Название приоритета. */
  name: string
}

/**
 * Элемент справочника навыков (квалификаций).
 */
export type SkillSelectorItem = {
  /** Код навыка. */
  code: string
  /** Название навыка. */
  name: string
}

/**
 * Элемент справочника норм времени на выполнение работ.
 */
export type TimeNormSelectorItem = {
  /** Код нормы времени. */
  code: string
  /** Название нормы. */
  name: string
  /** Время на дорогу до клиента, в минутах. */
  road_to_client_min: number
  /** Время на технические работы, в минутах. */
  technical_work_min: number
  /** Время на оформление документов, в минутах. */
  documents_min: number
  /** Базовая норма времени, в минутах. */
  base_norm_min: number
}

/**
 * Элемент справочника типов транспортных средств.
 */
export type VehicleTypeSelectorItem = {
  /** Код типа транспорта. */
  code: string
  /** Название типа транспорта. */
  name: string
}
