import type { HTTP_METHODS } from "@/utils/consts.ts";

export type RequestParamValue = string | number | boolean
export type RequestQueryValue = string | number | boolean | string[]
export type RequestParams = Record<string, RequestParamValue>
export type RequestQuery = Record<string, RequestQueryValue>

export type RequestErrorObject = {
  [key: string]: string | string[]
}

export interface ISuccessResponse<T> {
  isSuccess: true
  statusCode: number
  data: T
}

export interface IErrorResponse {
  isSuccess: false
  statusCode: number
  data: RequestErrorObject
}

export type RequestResponse<T> = ISuccessResponse<T> | IErrorResponse

export type RequestMethod = `${HTTP_METHODS}`

export type UrlEntry = {
  path: string
  method: RequestMethod
  isFormData?: boolean
  isEmptyResponse?: boolean
}
