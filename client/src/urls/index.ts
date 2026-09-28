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
  TASKS: {
    UPDATE_STATUS: {
      path: '/api/v2/jobs/status/',
      method: HTTP_METHODS.PATCH,
    },
    CREATE: {
      path: '/api/v2/tasks/',
      method: HTTP_METHODS.POST,
    },
    EXPLAIN: {
      path: '/api/v2/explain/{task_id}/',
      method: HTTP_METHODS.POST,
    },
    REASSIGNMENT: {
      PREVIEW: {
        path: '/api/v2/manual-reassignment/preview/',
        method: HTTP_METHODS.POST,
      },
      CONFIRM: {
        path: '/api/v2/manual-reassignment/confirm/',
        method: HTTP_METHODS.POST,
      },
    },
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
    REPLAN: {
      path: '/api/v2/replan/',
      method: HTTP_METHODS.POST,
    },
  },
}

export default baseUrls
