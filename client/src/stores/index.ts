import { createBaseResponseStore } from '@/utils/store.ts'
import type { DefaultDatasetApiResponse, OptimizeApiResponse } from '@/types/entities.ts'
import baseUrls from '@/urls'

export const useDefaultDatasetStore = createBaseResponseStore<DefaultDatasetApiResponse>({
  storeId: 'defaultDataset',
  url: baseUrls.DEFAULT,
})

export const useOptimizationStore = createBaseResponseStore<OptimizeApiResponse>({
  storeId: 'optimizeResponse',
  url: baseUrls.OPTIMIZE,
})
