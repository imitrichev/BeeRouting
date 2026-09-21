import { HTTP_METHODS } from '@/utils/consts.ts'

const baseUrls = {
  DEFAULT: {
    path: '/api/dataset/official/',
    method: HTTP_METHODS.GET,
  },
  UPLOAD: {
    path: '/api/dataset/upload/',
    method: HTTP_METHODS.POST,
  },
  OPTIMIZE: {
    path: '/api/optimize/',
    method: HTTP_METHODS.POST,
  },
}

export default baseUrls
