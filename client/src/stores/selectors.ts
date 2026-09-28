/**
 * Pinia-стор справочников (selectors).
 *
 * Загружает и кэширует в памяти справочники, используемые в фильтрах и формах:
 * территории, районы, приоритеты, навыки, нормы времени и типы транспорта.
 *
 * Каждый справочник представлен парой «список + флаг загрузки» и функцией
 * `load*`, которая выполняет запрос и заполняет список при успехе.
 * При ошибке запроса список не изменяется.
 *
 * Обратите внимание: при повторном вызове `load*` данные перезапрашиваются
 * (кэш не проверяется) — вызывающий код должен сам решать, когда обновлять.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sendRequest } from '@/utils/requests.ts'
import baseUrls from '@/urls'
import type {
  DistrictSelectorItem,
  PrioritySelectorItem,
  SkillSelectorItem,
  TerritorySelectorItem,
  TimeNormSelectorItem,
  VehicleTypeSelectorItem,
} from '@/types/selectors.ts'

/**
 * Стор справочников.
 */
export const useSelectorsStore = defineStore('selectors', () => {
  // --- Территории ---------------------------------------------------------

  /** Флаг загрузки справочника территорий. */
  const loadingTerritories = ref<boolean>(false)
  /** Список территорий. */
  const territories = ref<TerritorySelectorItem[]>([])

  /**
   * Загружает справочник территорий.
   * При успешном ответе обновляет `territories` и сбрасывает флаг загрузки.
   */
  const loadTerritories = async () => {
    loadingTerritories.value = true
    const response = await sendRequest<TerritorySelectorItem[]>(baseUrls.SELECTORS.TERRITORIES)
    if (response.isSuccess) {
      territories.value = response.data
      loadingTerritories.value = false
    }
  }

  // --- Районы -------------------------------------------------------------

  /** Флаг загрузки справочника районов. */
  const loadingDistricts = ref<boolean>(false)
  /** Список районов. */
  const districts = ref<DistrictSelectorItem[]>([])

  /**
   * Загружает справочник районов.
   * При успешном ответе обновляет `districts` и сбрасывает флаг загрузки.
   */
  const loadDistricts = async () => {
    loadingDistricts.value = true
    const response = await sendRequest<DistrictSelectorItem[]>(baseUrls.SELECTORS.DISTRICTS)
    if (response.isSuccess) {
      districts.value = response.data
      loadingDistricts.value = false
    }
  }

  // --- Приоритеты ---------------------------------------------------------

  /** Флаг загрузки справочника приоритетов. */
  const loadingPriorities = ref<boolean>(false)
  /** Список приоритетов. */
  const priorities = ref<PrioritySelectorItem[]>([])

  /**
   * Загружает справочник приоритетов.
   * При успешном ответе обновляет `priorities` и сбрасывает флаг загрузки.
   */
  const loadPriorities = async () => {
    loadingPriorities.value = true
    const response = await sendRequest<PrioritySelectorItem[]>(baseUrls.SELECTORS.PRIORITIES)
    if (response.isSuccess) {
      priorities.value = response.data
      loadingPriorities.value = false
    }
  }

  // --- Навыки -------------------------------------------------------------

  /** Флаг загрузки справочника навыков. */
  const loadingSkills = ref<boolean>(false)
  /** Список навыков. */
  const skills = ref<SkillSelectorItem[]>([])

  /**
   * Загружает справочник навыков.
   * При успешном ответе обновляет `skills` и сбрасывает флаг загрузки.
   */
  const loadSkills = async () => {
    loadingSkills.value = true
    const response = await sendRequest<SkillSelectorItem[]>(baseUrls.SELECTORS.SKILLS)
    if (response.isSuccess) {
      skills.value = response.data
      loadingSkills.value = false
    }
  }

  // --- Нормы времени ------------------------------------------------------

  /** Флаг загрузки справочника норм времени. */
  const loadingTimeNorms = ref<boolean>(false)
  /** Список норм времени. */
  const timeNorms = ref<TimeNormSelectorItem[]>([])

  /**
   * Загружает справочник норм времени.
   * При успешном ответе обновляет `timeNorms` и сбрасывает флаг загрузки.
   */
  const loadTimeNorms = async () => {
    loadingTimeNorms.value = true
    const response = await sendRequest<TimeNormSelectorItem[]>(baseUrls.SELECTORS.TIME_NORMS)
    if (response.isSuccess) {
      timeNorms.value = response.data
      loadingTimeNorms.value = false
    }
  }

  // --- Типы транспорта ----------------------------------------------------

  /** Флаг загрузки справочника типов транспорта. */
  const loadingVehicleTypes = ref<boolean>(false)
  /** Список типов транспорта. */
  const vehicleTypes = ref<VehicleTypeSelectorItem[]>([])

  /**
   * Загружает справочник типов транспорта.
   * При успешном ответе обновляет `vehicleTypes` и сбрасывает флаг загрузки.
   */
  const loadVehicleTypes = async () => {
    loadingVehicleTypes.value = true
    const response = await sendRequest<VehicleTypeSelectorItem[]>(baseUrls.SELECTORS.VEHICLE_TYPES)
    if (response.isSuccess) {
      vehicleTypes.value = response.data
      loadingVehicleTypes.value = false
    }
  }

  return {
    loadingTerritories,
    territories,
    loadTerritories,

    loadingDistricts,
    districts,
    loadDistricts,

    loadingPriorities,
    priorities,
    loadPriorities,

    loadingSkills,
    skills,
    loadSkills,

    loadingTimeNorms,
    timeNorms,
    loadTimeNorms,

    loadingVehicleTypes,
    vehicleTypes,
    loadVehicleTypes,
  }
})
