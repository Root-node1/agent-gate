export interface AuthUser {
  username: string
}

export type AuthStatus =
  | { authenticated: false }
  | { authenticated: true; user: AuthUser }

export interface AuthOptions {
  csrfToken: string
  googleOAuthEnabled: boolean
  githubOAuthEnabled: boolean
}

export type LoginResult =
  | { kind: 'authenticated' }
  | { kind: 'mfa'; types: string[] }
  | { kind: 'verify-email' }

export interface HeadlessResponse {
  status: number
  data?: unknown
  meta?: Record<string, unknown>
  errors?: Array<{ message?: string; param?: string; code?: string }>
}

const HEADLESS = '/api/auth/_allauth/browser/v1'

export class AuthError extends Error {
  readonly status: number
  readonly fieldErrors: Record<string, string>
  readonly responseData: unknown

  constructor(
    message: string,
    status: number,
    fieldErrors: Record<string, string> = {},
    responseData?: unknown,
  ) {
    super(message)
    this.status = status
    this.fieldErrors = fieldErrors
    this.responseData = responseData
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function responseBody(response: Response): Promise<Record<string, unknown>> {
  const body: unknown = await response.json().catch(() => ({}))
  return isRecord(body) ? body : {}
}

function errorFromResponse(body: Record<string, unknown>, status: number, fallback: string) {
  const errors = Array.isArray(body.errors) ? body.errors : []
  const fieldErrors: Record<string, string> = {}
  let firstMessage: string | null = null
  for (const item of errors) {
    if (!isRecord(item) || typeof item.message !== 'string') continue
    firstMessage ??= item.message
    if (typeof item.param === 'string') fieldErrors[item.param] = item.message
  }
  return new AuthError(firstMessage ?? fallback, status, fieldErrors, body.data)
}

async function csrfToken(): Promise<string> {
  const response = await fetch('/api/auth/csrf/', { credentials: 'same-origin' })
  const body = await responseBody(response)
  if (!response.ok || typeof body.csrfToken !== 'string') {
    throw new AuthError('Could not prepare a secure authentication request.', response.status)
  }
  return body.csrfToken
}

async function headlessRequest(
  path: string,
  method = 'GET',
  body?: unknown,
  headers: Record<string, string> = {},
  allowedStatuses: number[] = [],
): Promise<HeadlessResponse> {
  const requestHeaders = new Headers(headers)
  const init: RequestInit = { method, credentials: 'same-origin', headers: requestHeaders }

  if (method !== 'GET' && method !== 'HEAD') {
    requestHeaders.set('X-CSRFToken', await csrfToken())
  }
  if (body !== undefined) {
    requestHeaders.set('Content-Type', 'application/json')
    init.body = JSON.stringify(body)
  }

  const response = await fetch(`${HEADLESS}/${path}`, init)
  const payload = await responseBody(response)
  if (!isRecord(payload) || typeof payload.status !== 'number') {
    throw new AuthError('The authentication service returned an invalid response.', response.status)
  }

  const result = payload as unknown as HeadlessResponse
  if (!response.ok && !allowedStatuses.includes(response.status)) {
    throw errorFromResponse(payload, response.status, 'The authentication request failed.')
  }
  return result
}

export async function getAuthOptions(): Promise<AuthOptions> {
  const response = await fetch('/api/auth/options/', { credentials: 'same-origin' })
  const body = await responseBody(response)
  if (
    response.ok &&
    typeof body.csrfToken === 'string' &&
    typeof body.googleOAuthEnabled === 'boolean' &&
    typeof body.githubOAuthEnabled === 'boolean'
  ) {
    return {
      csrfToken: body.csrfToken,
      googleOAuthEnabled: body.googleOAuthEnabled,
      githubOAuthEnabled: body.githubOAuthEnabled,
    }
  }
  throw new AuthError(
    typeof body.detail === 'string' ? body.detail : 'Could not load sign-in options.',
    response.status,
  )
}

export async function getAuthStatus(): Promise<AuthStatus> {
  const response = await fetch('/api/auth/session/', { credentials: 'same-origin' })
  const body = await responseBody(response)
  if (!response.ok) {
    throw new AuthError(
      typeof body.detail === 'string' ? body.detail : 'Could not verify the dashboard session.',
      response.status,
    )
  }
  if (body.authenticated === true && isRecord(body.user) && typeof body.user.username === 'string') {
    return { authenticated: true, user: { username: body.user.username } }
  }
  if (body.authenticated === false) return { authenticated: false }
  throw new AuthError('The backend returned an invalid session response.', response.status)
}

function getFlows(response: HeadlessResponse): Array<Record<string, unknown>> {
  if (!isRecord(response.data) || !Array.isArray(response.data.flows)) return []
  return response.data.flows.filter(isRecord)
}

export async function signIn(email: string, password: string): Promise<LoginResult> {
  const response = await headlessRequest(
    'auth/login',
    'POST',
    { email, password },
    {},
    [401],
  )
  if (response.meta?.is_authenticated === true) return { kind: 'authenticated' }

  const flows = getFlows(response)
  const pending = flows.find((flow) => flow.is_pending === true)
  if (pending?.id === 'mfa_authenticate') {
    return {
      kind: 'mfa',
      types: Array.isArray(pending.types)
        ? pending.types.filter((type): type is string => typeof type === 'string')
        : [],
    }
  }
  if (pending?.id === 'verify_email') return { kind: 'verify-email' }
  throw new AuthError('The account needs another verification step.', response.status)
}

export async function verifyMfa(code: string): Promise<void> {
  const response = await headlessRequest('auth/2fa/authenticate', 'POST', { code }, {}, [401])
  if (response.meta?.is_authenticated !== true) {
    throw new AuthError('The verification code was not accepted.', response.status)
  }
}

export async function signUp(input: {
  email: string
  password: string
  full_name: string
  organization: string
  accept_terms: boolean
}): Promise<void> {
  await headlessRequest('auth/signup', 'POST', input, {}, [401])
}

export async function verifyEmail(key: string): Promise<void> {
  await headlessRequest('auth/email/verify', 'POST', { key })
}

export async function resendVerificationCode(): Promise<void> {
  await headlessRequest('auth/email/verify/resend', 'POST')
}

export async function changeVerificationEmail(email: string): Promise<void> {
  await headlessRequest('account/email', 'POST', { email })
}

export async function requestPasswordReset(email: string): Promise<void> {
  await headlessRequest('auth/password/request', 'POST', { email })
}

export async function validatePasswordResetKey(key: string): Promise<void> {
  await headlessRequest(
    'auth/password/reset',
    'GET',
    undefined,
    { 'X-Password-Reset-Key': key },
  )
}

export async function resetPassword(key: string, password: string): Promise<void> {
  await headlessRequest('auth/password/reset', 'POST', { key, password }, {}, [401])
}

export async function reauthenticate(password: string): Promise<void> {
  await headlessRequest('auth/reauthenticate', 'POST', { password })
}

export async function setRememberSession(remember: boolean): Promise<void> {
  const token = await csrfToken()
  const response = await fetch('/api/auth/session/remember/', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify({ remember }),
  })
  const body = await responseBody(response)
  if (!response.ok) {
    throw new AuthError(
      typeof body.detail === 'string' ? body.detail : 'Could not update session duration.',
      response.status,
    )
  }
}

export async function getAuthenticators(): Promise<unknown[]> {
  const response = await headlessRequest('account/authenticators')
  if (!Array.isArray(response.data)) {
    throw new AuthError('The authentication service returned invalid authenticator data.', 502)
  }
  return response.data
}

export async function getTotpSetup(): Promise<{
  active: boolean
  secret?: string
  totpUrl?: string
}> {
  const response = await headlessRequest(
    'account/authenticators/totp',
    'GET',
    undefined,
    {},
    [404],
  )
  if (response.status === 404) {
    if (typeof response.meta?.secret !== 'string' || typeof response.meta?.totp_url !== 'string') {
      throw new AuthError('The authentication service returned invalid TOTP setup data.', 502)
    }
    return { active: false, secret: response.meta.secret, totpUrl: response.meta.totp_url }
  }
  return { active: true }
}

export async function activateTotp(code: string): Promise<void> {
  await headlessRequest('account/authenticators/totp', 'POST', { code })
}

export async function removeTotp(): Promise<void> {
  await headlessRequest('account/authenticators/totp', 'DELETE')
}

export async function generateRecoveryCodes(): Promise<string[]> {
  const response = await headlessRequest('account/authenticators/recovery-codes', 'POST', {})
  if (!isRecord(response.data) || !Array.isArray(response.data.unused_codes)) {
    throw new AuthError('The authentication service did not return recovery codes.', 502)
  }
  return response.data.unused_codes.filter((code): code is string => typeof code === 'string')
}

export async function getRecoveryCodes(): Promise<string[] | null> {
  const response = await headlessRequest(
    'account/authenticators/recovery-codes',
    'GET',
    undefined,
    {},
    [404],
  )
  if (response.status === 404) return null
  if (!isRecord(response.data) || !Array.isArray(response.data.unused_codes)) return []
  return response.data.unused_codes.filter((code): code is string => typeof code === 'string')
}

export async function signOut(): Promise<void> {
  const token = await csrfToken()
  const response = await fetch('/api/auth/logout/', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': token },
  })
  if (!response.ok) {
    const body = await responseBody(response)
    throw new AuthError(
      typeof body.detail === 'string' ? body.detail : 'Sign-out failed.',
      response.status,
    )
  }
}
