/**
 * Типы для работы с HTTP-запросами: параметры, query, методы, URL-описания
 * и унифицированные структуры успешных/ошибочных ответов.
 *
 * Модуль содержит только декларации типов и не имеет runtime-кода.
 */

import type { HTTP_METHODS } from '@/utils/consts.ts'

/**
 * Допустимое значение параметра пути (path-параметр).
 */
export type RequestParamValue = string | number | boolean

/**
 * Допустимое значение query-параметра. Массивы строк сериализуются в повторяющиеся ключи.
 */
export type RequestQueryValue = string | number | boolean | string[]

/**
 * Набор path-параметров запроса.
 */
export type RequestParams = Record<string, RequestParamValue>

/**
 * Набор query-параметров запроса.
 */
export type RequestQuery = Record<string, RequestQueryValue>

/**
 * Тело ошибки от API: соответствие "поле → сообщение(я)".
 * Значение может быть строкой или массивом строк (например, для ошибок валидации).
 */
export type RequestErrorObject = {
  [key: string]: string | string[]
}

/**
 * Успешный ответ API.
 *
 * @template T Тип полезной нагрузки в поле `data`.
 */
export interface ISuccessResponse<T> {
  /** Дискриминант успешного ответа. */
  isSuccess: true
  /** HTTP-код ответа. */
  statusCode: number
  /** Полезная нагрузка ответа. */
  data: T
}

/**
 * Ошибочный ответ API.
 */
export interface IErrorResponse {
  /** Дискриминант ошибочного ответа. */
  isSuccess: false
  /** HTTP-код ответа. */
  statusCode: number
  /** Тело ошибки. */
  data: RequestErrorObject
}

/**
 * Унифицированный ответ API: успешный или ошибочный.
 *
 * @template T Тип полезной нагрузки успешного ответа.
 */
export type RequestResponse<T> = ISuccessResponse<T> | IErrorResponse

/**
 * HTTP-метод запроса, ограниченный значениями из `HTTP_METHODS`.
 */
export type RequestMethod = `${HTTP_METHODS}`

/**
 * Описание конечной точки (endpoint) API.
 */
export type UrlEntry = {
  /** Путь запроса (может содержать шаблонные сегменты, например `/tasks/:id`). */
  path: string
  /** HTTP-метод. */
  method: RequestMethod
  /** Признак того, что тело запроса передаётся как `FormData`. */
  isFormData?: boolean
  /** Признак того, что ответ не содержит тела (например, 204 No Content). */
  isEmptyResponse?: boolean
}
