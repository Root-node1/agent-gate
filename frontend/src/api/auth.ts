/**
 * Unified client for the AgentGate authentication contract.
 *
 * Backend contract (all authoritative under /api/auth/):
 *
 * Allauth headless JSON (session-cookie based):
 *   POST /api/auth/headless/browser/v1/auth/login
 *   POST /api/auth/headless/browser/v1/auth/signup
 *   POST /api/auth/headless/browser/v1/auth/password/request
 *   POST /api/auth/headless/browser/v1/auth/password/reset
 *   GET  /api/auth/headless/browser/v1/auth/session
 *   POST /api/auth/headless/browser/v1/account/password/change
 *   GET/POST/DELETE /api/auth/headless/browser/v1/account/authenticators/totp
 *   POST  /api/auth/headless/browser/v1/account/authenticators/recovery-codes
 *   GET   /api/auth/headless/browser/v1/account/authenticators/recovery-codes
 *
 * Custom session endpoints:
 *   GET  /api/auth/csrf/          -> { csrfToken }
 *   GET  /api/auth/options/       -> { csrfToken, googleOAuthEnabled, githubOAuthEnabled }
 *   GET  /api/auth/session/       -> { authenticated, user?: { username } }
 *   POST /api/auth/session/remember/ -> { remember }
 *   POST /api/auth/logout/        -> 204
 *
 * Dashboard user endpoints:
 *   GET  /api/auth/user/          -> CurrentUserSerializer (includes profile)
 *   GET/PATCH /api/auth/profile/  -> AccountProfileSerializer
 *
 * Every request carries `credentials: "include"` and a CSRF token read
 * from the `csrftoken` cookie.
 */

export interface HeadlessBody {
  status: number
  errors?: Array<{ code?: string; param?: string; message: string }>
  data?: Record<string, unknown>
  meta?: { is_authenticated?: boolean }
  flows?: Array<{ id: string }>
}

export interface HeadlessError extends Error {
  status: number
  fieldErrors: Record<string, string>
  is_authenticated: boolean | null
}

export function createHeadlessError(message: string, body: HeadlessBody): HeadlessError {
  const fieldErrors: Record<string, string> = {}
  if (body.errors) {
    for (const err of body.errors) {
      const field = err.param || (err.code === 'invalid_password_reset' ? 'key' : 'non_field')
      fieldErrors[field] = err.message
    }
  }
  const err: HeadlessError = new Error(message) as HeadlessError
  err.name = 'HeadlessError'
  err.status = body.status
  err.fieldErrors = fieldErrors
  err.is_authenticated = body.meta?.is_authenticated ?? null
  return err
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/\\+^])/g, '\\$1') + '=([^;]*)'),
  )
  return match ? decodeURIComponent(match[1]) : null
}

const HEADLESS_BASE = '/api/auth/headless/browser/v1'

export async function bootstrapCsrf(): Promise<void> {
  const res = await fetch(`${HEADLESS_BASE}/config`, { credentials: 'include' })
  if (!res.ok) throw new Error('Could not initialize the authentication session.')
}

export async function headlessFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = typeof document === 'undefined' ? null : getCookie('csrftoken')
  const headers = new Headers(init.headers)
  if (token && !headers.has('X-CSRFToken')) headers.set('X-CSRFToken', token)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  let res: Response
  try {
    res = await fetch(HEADLESS_BASE + path, {
      ...init,
      credentials: 'include',
      headers,
    })
  } catch {
    throw createHeadlessError(
      'Cannot reach the backend. Is it running on port 8000?',
      { status: 0 },
    )
  }
  return res
}

/** GET /auth/session -> 200 when authenticated, 401 otherwise. */
export async function getSession(): Promise<HeadlessBody> {
  const res = await headlessFetch('/auth/session')
  const body = (await res.json().catch(() => ({}))) as HeadlessBody
  body.status = res.status
  return body
}

/** Request a password-reset email. Always resolves (allauth returns 200 whether
 * or not the account exists, to prevent enumeration). Rejects only on transport
 * errors or rate limiting (429). */
export async function requestPasswordReset(email: string): Promise<void> {
  const res = await headlessFetch('/auth/password/request', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
  const body = (await res.json().catch(() => ({}))) as HeadlessBody
  body.status = res.status
  if (!res.ok) throw createHeadlessError('Could not send the reset email.', body)
}

/**
 * Confirm a password reset. The reset-confirm endpoint is an *anonymous*
 * operation: allauth returns 401 (meta.is_authenticated=false, no errors) on
 * success and 400 (with `errors`) on failure. Callers must NOT treat a 401 here
 * as a failure.
 *
 * Resolves to the response of the new password being live.
 */
export async function confirmPasswordReset(key: string, password: string): Promise<void> {
  const res = await headlessFetch('/auth/password/reset', {
    method: 'POST',
    body: JSON.stringify({ key, password }),
  })
  const body = (await res.json().catch(() => ({}))) as HeadlessBody
  body.status = res.status
  if (!res.ok && res.status !== 401) {
    throw createHeadlessError(
      res.status === 429
        ? 'Too many reset attempts. Please wait a moment and try again.'
        : 'The password reset link is invalid or expired.',
      body,
    )
  }
}

/** Change the password of the currently authenticated (session) user. */
export async function changePassword(current: string, next: string): Promise<void> {
  const res = await headlessFetch('/account/password/change', {
    method: 'POST',
    body: JSON.stringify({ current_password: current, new_password: next }),
  })
  const body = (await res.json().catch(() => ({}))) as HeadlessBody
  body.status = res.status
  if (res.status === 401) {
    throw createHeadlessError('You must be logged in to change your password.', body)
  }
  if (!res.ok) throw createHeadlessError('Could not change the password.', body)
}

// ---------------------------------------------------------------------------
// Custom session contract (smallest extensions needed by the dashboard SPA)
// ---------------------------------------------------------------------------

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

interface HeadlessResponse {
  status: number
  data?: unknown
  meta?: Record<string, unknown>
  errors?: Array<{ message?: string; param?: string; code?: string }>
}

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
  const init: RequestInit = { method, credentials: 'include', headers: requestHeaders }

  if (method !== 'GET' && method !== 'HEAD') {
    requestHeaders.set('X-CSRFToken', await csrfToken())
  }
  if (body !== undefined) {
    requestHeaders.set('Content-Type', 'application/json')
    init.body = JSON.stringify(body)
  }

  const response = await fetch(`${HEADLESS_BASE}/${path}`, init)
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
      csrfToken: body.csrfToken as string,
      googleOAuthEnabled: body.googleOAuthEnabled as boolean,
      githubOAuthEnabled: body.githubOAuthEnabled as boolean,
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
    return { authenticated: true, user: { username: body.user.username as string } }
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

export async function reauthenticate(password: string): Promise<void> {
  await headlessRequest('auth/reauthenticate', 'POST', { password }, {}, [401])
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
    return { active: false, secret: response.meta.secret as string, totpUrl: response.meta.totp_url as string }
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
