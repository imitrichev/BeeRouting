import { HTTP_METHODS } from '@/utils/consts.ts'

const baseUrls = {
  SELECTORS: {
    TERRITORIES: {
      path: '/api/v2/selectors/territories/',
      method: HTTP_METHODS.GET,
    },
    DISTRICTS: {
      path: '/api/v2/selectors/districts/',
      method: HTTP_METHODS.GET,
    },
    PRIORITIES: {
      path: '/api/v2/selectors/priorities/',
      method: HTTP_METHODS.GET,
    },
    SKILLS: {
      path: '/api/v2/selectors/skills/',
      method: HTTP_METHODS.GET,
    },
    TIME_NORMS: {
      path: '/api/v2/selectors/time-norms/',
      method: HTTP_METHODS.GET,
    },
    VEHICLE_TYPES: {
      path: '/api/v2/selectors/vehicle-types/',
      method: HTTP_METHODS.GET,
    },
  },
  RESET_ALL: {
    path: '/api/v2/dataset/official/',
    method: HTTP_METHODS.POST,
  },
  DISTRICT: {
    DATA: {
      path: '/api/v2/dataset/',
      method: HTTP_METHODS.GET,
    },
    OPTIMIZE: {
      path: '/api/v2/optimize/',
      method: HTTP_METHODS.POST,
    },
  },
}

export default baseUrls
