import { CsrfBootstrapError, getCsrfToken } from './csrf'

export const SESSION_EXPIRED_EVENT = 'agentgate:session-expired'

export type ApiDetails = Record<string, unknown>
export type ApiFieldErrors = Record<string, string[]>

export class ApiError extends Error {
  readonly status: number
  readonly code: string | null
  readonly details: ApiDetails
  readonly requestId: string | null
  readonly fieldErrors: ApiFieldErrors

  constructor(
    message: string,
    status: number,
    code: string | null = null,
    details: ApiDetails = {},
    requestId: string | null = null,
    fieldErrors: ApiFieldErrors = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
    this.fieldErrors = fieldErrors
  }
}

export class SessionExpiredError extends ApiError {
  constructor(message: string, requestId: string | null = null) {
    super(message, 401, 'authentication_failed', {}, requestId)
    this.name = 'SessionExpiredError'
  }
}

export interface ApiRequestOptions {
  method?: string
  body?: unknown
  headers?: HeadersInit
  signal?: AbortSignal
  auth?: 'session' | 'agent' | 'none'
  agentKey?: string
  allowEmptyResponse?: boolean
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fieldErrorsFrom(details: ApiDetails): ApiFieldErrors {
  const result: ApiFieldErrors = {}
  for (const [field, value] of Object.entries(details)) {
    if (Array.isArray(value)) {
      const messages = value.filter((item): item is string => typeof item === 'string')
      if (messages.length) result[field] = messages
    } else if (typeof value === 'string') {
      result[field] = [value]
    }
  }
  return result
}

function parseError(
  payload: unknown,
  status: number,
  requestId: string | null,
): ApiError {
  const root = isRecord(payload) ? payload : {}
  const envelope = isRecord(root.error) ? root.error : null
  const details = isRecord(envelope?.details)
    ? envelope.details
    : isRecord(root.details)
      ? root.details
      : Object.fromEntries(
          Object.entries(root).filter(([key]) => !['detail', 'request_id', 'error'].includes(key)),
        )
  const message =
    (typeof envelope?.message === 'string' && envelope.message) ||
    (typeof root.detail === 'string' && root.detail) ||
    `Request failed (HTTP ${status}).`
  const code =
    (typeof envelope?.code === 'string' && envelope.code) ||
    (typeof root.code === 'string' && root.code) ||
    null
  return new ApiError(
    message,
    status,
    code,
    details,
    (typeof root.request_id === 'string' && root.request_id) || requestId,
    fieldErrorsFrom(details),
  )
}

async function responsePayload(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

function notifySessionExpired() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
  }
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const auth = options.auth ?? 'session'
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  let body: BodyInit | undefined

  if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(options.body)
  }

  if (auth === 'session' && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    try {
      headers.set('X-CSRFToken', await getCsrfToken())
    } catch (error) {
      if (error instanceof CsrfBootstrapError) {
        throw new ApiError(error.message, error.status, 'csrf_failed')
      }
      throw error
    }
  }
  if (auth === 'agent') {
    if (!options.agentKey) throw new ApiError('An agent API key is required.', 0)
    headers.set('Authorization', `Bearer ${options.agentKey}`)
  }

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      body,
      signal: options.signal,
      credentials: auth === 'session' ? 'include' : 'omit',
    })
  } catch (error) {
    if (options.signal?.aborted || (error instanceof Error && error.name === 'AbortError')) {
      throw error
    }
    throw new ApiError(
      'Cannot reach the AgentGate API. Check your connection and try again.',
      0,
      'network_error',
    )
  }

  const payload = await responsePayload(response)
  const requestId = response.headers.get('X-Request-Id')
  if (!response.ok) {
    const error = parseError(payload, response.status, requestId)
    if (response.status === 401 && auth === 'session') {
      notifySessionExpired()
      throw new SessionExpiredError(error.message, error.requestId)
    }
    throw error
  }
  if (response.status === 204 || payload === null) {
    if (options.allowEmptyResponse) return undefined as T
    throw new ApiError(
      'The API returned an empty response where JSON was expected.',
      response.status,
      'invalid_response',
      {},
      requestId,
    )
  }
  return payload as T
}
