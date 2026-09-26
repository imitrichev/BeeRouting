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

export const useSelectorsStore = defineStore('selectors', () => {
  const loadingTerritories = ref<boolean>(false)
  const territories = ref<TerritorySelectorItem[]>([])
  const loadTerritories = async () => {
    loadingTerritories.value = true
    const response = await sendRequest<TerritorySelectorItem[]>(baseUrls.SELECTORS.TERRITORIES)
    if (response.isSuccess) {
      territories.value = response.data
      loadingTerritories.value = false
    }
  }

  const loadingDistricts = ref<boolean>(false)
  const districts = ref<DistrictSelectorItem[]>([])
  const loadDistricts = async () => {
    loadingDistricts.value = true
    const response = await sendRequest<DistrictSelectorItem[]>(baseUrls.SELECTORS.DISTRICTS)
    if (response.isSuccess) {
      districts.value = response.data
      loadingDistricts.value = false
    }
  }

  const loadingPriorities = ref<boolean>(false)
  const priorities = ref<PrioritySelectorItem[]>([])
  const loadPriorities = async () => {
    loadingPriorities.value = true
    const response = await sendRequest<PrioritySelectorItem[]>(baseUrls.SELECTORS.PRIORITIES)
    if (response.isSuccess) {
      priorities.value = response.data
      loadingPriorities.value = false
    }
  }

  const loadingSkills = ref<boolean>(false)
  const skills = ref<SkillSelectorItem[]>([])
  const loadSkills = async () => {
    loadingSkills.value = true
    const response = await sendRequest<SkillSelectorItem[]>(baseUrls.SELECTORS.SKILLS)
    if (response.isSuccess) {
      skills.value = response.data
      loadingSkills.value = false
    }
  }

  const loadingTimeNorms = ref<boolean>(false)
  const timeNorms = ref<TimeNormSelectorItem[]>([])
  const loadTimeNorms = async () => {
    loadingTimeNorms.value = true
    const response = await sendRequest<TimeNormSelectorItem[]>(baseUrls.SELECTORS.TIME_NORMS)
    if (response.isSuccess) {
      timeNorms.value = response.data
      loadingTimeNorms.value = false
    }
  }

  const loadingVehicleTypes = ref<boolean>(false)
  const vehicleTypes = ref<VehicleTypeSelectorItem[]>([])
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
