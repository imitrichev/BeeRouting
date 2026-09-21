import { defineStore } from 'pinia'
import type { UrlEntry } from '@/types/requests.ts'
import { computed, readonly, ref, type Ref } from 'vue'
import type { RequestParams, RequestQuery } from '@/types/requests.ts'
import { executeWithMinDuration, sendRequest } from '@/utils/requests.ts'

type BaseActionStore<TData extends object> = {
  getLoading: Ref<boolean>
  execute: (data: TData, params?: RequestParams, query?: RequestQuery) => Promise<void>
}

export type BaseResponseStore<TData extends object> = {
  getLoading: Ref<boolean>
  getData: Ref<TData | null>
  execute: (data: object, params?: RequestParams, query?: RequestQuery) => Promise<void>
  isErrorResponse: Ref<boolean>
  isNotFoundResponse: Ref<boolean>
}

type StoreOptions = {
  storeId: string
  url: UrlEntry
}

export function createBaseResponseStore<T extends object>(options: StoreOptions) {
  const { storeId, url } = options

  return defineStore(storeId, () => {
    const loading = ref<boolean>(false)
    const item = ref<T | null>(null)
    const statusCode = ref<number | null>(null)
    const getLoading = readonly(loading)
    const getData = computed(() => item.value)

    const isErrorResponse = computed((): boolean => {
      const str = String(statusCode.value)
      return str[0] === '4' || str[0] === '5'
    })

    const isNotFoundResponse = computed((): boolean => {
      return isErrorResponse.value && statusCode.value === 404
    })

    const execute = async (
      data: object = {},
      params: RequestParams = {},
      query: RequestQuery = {},
    ): Promise<void> => {
      if (loading.value) return

      loading.value = true
      statusCode.value = null
      try {
        await executeWithMinDuration(async () => {
          const response = await sendRequest<T>(url, data, params, query)
          statusCode.value = response.statusCode
          if (!response.isSuccess) throw response.data
          item.value = response.data
        })
      } catch (error) {
        loading.value = false
      }
      loading.value = false
    }

    const baseStore: BaseResponseStore<T> = {
      getLoading,
      getData,
      isErrorResponse,
      isNotFoundResponse,
      execute,
    }

    return {
      ...baseStore,
    }
  })
}

export function createBaseActionStore<TData extends object>(options: StoreOptions) {
  const { storeId, url } = options

  return defineStore(storeId, () => {
    const loading = ref<boolean>(false)
    const getLoading = readonly(loading)

    const execute = async (
      data: TData = {} as TData,
      params: RequestParams = {},
      query: RequestQuery = {},
    ): Promise<void> => {
      if (loading.value) return

      loading.value = true
      try {
        await executeWithMinDuration(async () => {
          const response = await sendRequest<unknown>(url, data, params, query)
          if (!response.isSuccess) throw response.data
        })
      } catch (error) {
        loading.value = false
        throw error
      }
      loading.value = false
    }

    const baseStore: BaseActionStore<TData> = {
      getLoading,
      execute,
    }

    return {
      ...baseStore,
    }
  })
}
