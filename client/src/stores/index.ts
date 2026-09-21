import { createBaseResponseStore } from "@/utils/store.ts";
import type { DefaultDatasetApiResponse } from "@/types/entities.ts";
import baseUrls from "@/urls";

export const useDefaultDatasetStore = createBaseResponseStore<DefaultDatasetApiResponse>({
  storeId: 'defaultDataset',
  url: baseUrls.DEFAULT
})
