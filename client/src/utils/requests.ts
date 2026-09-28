/**
 * HTTP-клиент: сборка URL с path- и query-параметрами, отправка запросов
 * и нормализация ответов в единый формат `RequestResponse<T>`.
 *
 * Модуль не выбрасывает исключения на сетевые ошибки и HTTP-ошибки —
 * они возвращаются как `IErrorResponse`. Исключение составляет лишь
 * невозможность собрать URL (не заданы обязательные path-параметры).
 */

import { API_URL } from '@/utils/consts.ts'
import type {
  RequestErrorObject,
  RequestParams,
  RequestQuery,
  RequestQueryValue,
  RequestResponse,
} from '@/types/requests.ts'
import type { UrlEntry } from '@/types/requests.ts'

/**
 * Добавляет один query-параметр в URL.
 * Массивы разворачиваются в несколько одноимённых параметров.
 *
 * @param url   Целевой URL.
 * @param key   Имя параметра.
 * @param value Значение (строка/число/булево/массив строк).
 */
const appendSingleQueryParam = (url: URL, key: string, value: RequestQueryValue) => {
  if (Array.isArray(value)) {
    value.forEach((v) => url.searchParams.append(key, v))
    return
  }

  url.searchParams.append(key, String(value))
}

/**
 * Добавляет в URL все query-параметры, пропуская `null` и `undefined`.
 *
 * @param url   Целевой URL.
 * @param query Набор query-параметров.
 */
const appendQueryParams = (url: URL, query: RequestQuery) => {
  for (const key in query) {
    const value = query[key]
    if (value === null || value === undefined) continue
    appendSingleQueryParam(url, key, value)
  }
}

/**
 * Возвращает заголовки по умолчанию для запроса.
 * Для `FormData` заголовок `Content-Type` не задаётся — браузер
 * проставит его сам вместе с boundary.
 *
 * @param isFormData Признак передачи тела как `FormData`.
 * @returns Заголовки запроса.
 */
const getDefaultHeaders = (isFormData = false): HeadersInit => {
  if (isFormData) return {}
  return {
    'Content-Type': 'application/json',
  }
}

/**
 * Подставляет path-параметры вида `{name}` в шаблон пути и добавляет базовый URL.
 *
 * @param path   Шаблон пути (например, `/api/v2/explain/{task_id}/`).
 * @param params Значения path-параметров.
 * @returns Полный URL или `null`, если шаблон некорректен либо параметр не задан.
 */
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

/**
 * Пытается разобрать тело ошибочного ответа как JSON-объект.
 * Если тело не является объектом или парсинг не удался — возвращает текст
 * либо стандартное сообщение с HTTP-кодом.
 *
 * @param response Ответ fetch с `ok === false`.
 * @returns Объект с описанием ошибки.
 */
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

/**
 * Выполняет асинхронную функцию, гарантируя минимальную длительность её выполнения.
 * Используется для предотвращения «мигания» лоадеров при слишком быстрых ответах.
 *
 * @template T Тип результата.
 * @param fn      Функция, возвращающая промис.
 * @param minTime Минимальная длительность в миллисекундах (по умолчанию 200).
 * @returns Результат `fn` (или выбрасывает её ошибку после выдержки времени).
 */
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

/**
 * Отправляет HTTP-запрос по описанию endpoint'а и нормализует ответ.
 *
 * Поведение:
 * - `GET` — тело не отправляется;
 * - остальные методы — тело сериализуется в JSON либо передаётся как `FormData`;
 * - при `isEmptyResponse` тело ответа не читается, возвращается `{}` как `T`;
 * - сетевые ошибки и `AbortError` возвращаются как `IErrorResponse` со `statusCode: 0`.
 *
 * @template T Тип полезной нагрузки успешного ответа.
 * @param urlEntry Описание endpoint'а (path + method + флаги).
 * @param data     Тело запроса (объект или `FormData`).
 * @param params   Path-параметры для подстановки в шаблон пути.
 * @param query    Query-параметры.
 * @param signal   Опциональный `AbortSignal` для отмены запроса.
 * @returns Нормализованный ответ `RequestResponse<T>`.
 * @throws {Error} Если не удалось собрать URL (не заданы обязательные path-параметры).
 */
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
