import { API_URL } from '@/utils/consts.ts'
import type {
  RequestErrorObject,
  RequestParams,
  RequestQuery,
  RequestQueryValue,
  RequestResponse,
} from '@/types/requests.ts'
import type { UrlEntry } from '@/types/requests.ts'

const appendSingleQueryParam = (url: URL, key: string, value: RequestQueryValue) => {
  if (Array.isArray(value)) {
    value.forEach((v) => url.searchParams.append(key, v))
    return
  }

  url.searchParams.append(key, String(value))
}

const appendQueryParams = (url: URL, query: RequestQuery) => {
  for (const key in query) {
    const value = query[key]
    if (value === null || value === undefined) continue
    appendSingleQueryParam(url, key, value)
  }
}

const getDefaultHeaders = (isFormData = false): HeadersInit => {
  if (isFormData) return {}
  return {
    'Content-Type': 'application/json',
  }
}

const constructUrlStringWithParams = (path: string, params: RequestParams = {}) => {
  const parts = path.split('/')

  for (let i = 1; i < parts.length - 1; i++) {
    const part = parts[i]
    if (!part) {
      console.error('Ошибка подстановки параметров URL: пустая часть пути', path)
      return null
    }

    if (!part.startsWith('{')) continue

    const paramName = part.slice(1, -1)
    const paramValue = params[paramName]

    if (paramValue === undefined) {
      console.error(`Параметр "${paramName}" не задан при отправке запроса: ${path}`)
      return null
    }

    parts[i] = String(paramValue)
  }

  return `${API_URL}${parts.join('/')}`
}

const parseErrorResponse = async (response: Response): Promise<RequestErrorObject> => {
  try {
    const data = await response.json()
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      return data as RequestErrorObject
    }
    return { _error: 'Неизвестный формат ошибки' }
  } catch {
    const text = await response.text()
    return { _error: text || `HTTP ошибка ${response.status}` }
  }
}

export const executeWithMinDuration = async <T>(
  fn: () => Promise<T>,
  minTime: number = 200,
): Promise<T> => {
  const startTime = Date.now()
  let result: T
  let error: unknown

  try {
    result = await fn()
  } catch (e) {
    error = e
  }

  const elapsed = Date.now() - startTime
  if (elapsed < minTime) {
    await new Promise((resolve) => setTimeout(resolve, minTime - elapsed))
  }

  if (error !== undefined) {
    throw error
  }

  return result!
}

export const sendRequest = async <T>(
  urlEntry: UrlEntry,
  data: object | FormData = {},
  params: RequestParams = {},
  query: RequestQuery = {},
  signal?: AbortSignal,
): Promise<RequestResponse<T>> => {
  const urlString = constructUrlStringWithParams(urlEntry.path, params)

  if (!urlString) {
    throw new Error(`Не удалось собрать URL`)
  }

  const url = new URL(urlString)
  appendQueryParams(url, query)

  const headers = getDefaultHeaders(urlEntry.isFormData)

  let response
  try {
    if (urlEntry.method === 'GET') {
      response = await executeWithMinDuration(() =>
        fetch(url, {
          method: urlEntry.method,
          headers,
          signal,
        }),
      )
    } else {
      const body: BodyInit = urlEntry.isFormData ? (data as FormData) : JSON.stringify(data)
      response = await executeWithMinDuration(() =>
        fetch(url, {
          method: urlEntry.method,
          headers,
          body,
          signal,
        }),
      )
    }
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      return {
        isSuccess: false,
        statusCode: 0,
        data: { _error: 'Запрос был отменён' },
      }
    }

    return {
      isSuccess: false,
      statusCode: 0,
      data: {
        _error: 'Сетевая ошибка запроса',
      },
    }
  }

  if (!response.ok) {
    const errorData = await parseErrorResponse(response)
    return {
      isSuccess: false,
      statusCode: response.status,
      data: errorData,
    }
  }

  if (urlEntry.isEmptyResponse) {
    return {
      isSuccess: true,
      statusCode: response.status,
      data: {} as T,
    }
  }

  try {
    const responseData = (await response.json()) as T
    return {
      isSuccess: true,
      statusCode: response.status,
      data: responseData,
    }
  } catch {
    return {
      isSuccess: false,
      statusCode: response.status,
      data: { _error: 'Не удалось обработать ответ сервера' },
    }
  }
}
