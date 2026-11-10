/**
 * Browser client for django-allauth's headless JSON API.
 *
 * Authentication is held by the HttpOnly Django session cookie. Unsafe
 * requests bootstrap CSRF through allauth's config endpoint and send the
 * readable csrftoken cookie as X-CSRFToken.
 */

export interface HeadlessFlow {
  id: string
  is_pending?: boolean
  types?: string[]
}

export interface HeadlessBody {
  status: number
  errors?: Array<{ code?: string; param?: string; message: string }>
  data?: Record<string, unknown> | unknown[]
  meta?: Record<string, unknown> & {
    is_authenticated?: boolean
    secret?: string
    totp_url?: string
  }
}

export interface HeadlessError extends Error {
  status: number
  fieldErrors: Record<string, string>
  is_authenticated: boolean | null
  responseData: unknown
}

export interface CurrentUser {
  id: string
  email: string
  username: string
  first_name: string
  last_name: string
  date_joined: string
  is_email_verified: boolean
  memberships: Array<{ organization: string; role: string }>
}

export type AuthenticationState =
  | { status: 'authenticated'; body: HeadlessBody }
  | { status: 'anonymous'; body: HeadlessBody }
  | { status: 'pending'; flow: HeadlessFlow; body: HeadlessBody }

export type LoginResult =
  | { kind: 'authenticated' }
  | { kind: 'mfa'; types: string[] }
  | { kind: 'verify-email' }

const HEADLESS_BASE = '/api/auth/headless/browser/v1'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${escapedName}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

function headlessBody(payload: unknown, status: number): HeadlessBody {
  if (!isRecord(payload)) {
    throw createHeadlessError(
      'The authentication service returned an invalid response.',
      { status },
    )
  }

  const body: HeadlessBody = { status }
  if (isRecord(payload.data) || Array.isArray(payload.data)) body.data = payload.data
  if (isRecord(payload.meta)) body.meta = payload.meta
  if (Array.isArray(payload.errors)) {
    body.errors = payload.errors.filter(
      (error): error is { code?: string; param?: string; message: string } =>
        isRecord(error) && typeof error.message === 'string',
    )
  }
  return body
}

export function createHeadlessError(message: string, body: HeadlessBody): HeadlessError {
  const fieldErrors: Record<string, string> = {}
  for (const error of body.errors ?? []) {
    const field =
      error.param || (error.code === 'invalid_password_reset' ? 'key' : 'non_field')
    fieldErrors[field] = error.message
  }

  const err = new Error(message) as HeadlessError
  err.name = 'HeadlessError'
  err.status = body.status
  err.fieldErrors = fieldErrors
  err.is_authenticated =
    typeof body.meta?.is_authenticated === 'boolean' ? body.meta.is_authenticated : null
  err.responseData = body.data ?? null
  return err
}

function firstErrorMessage(body: HeadlessBody, fallback: string): string {
  return body.errors?.[0]?.message || fallback
}

function dataRecord(body: HeadlessBody): Record<string, unknown> | null {
  return isRecord(body.data) ? body.data : null
}

async function readBody(response: Response): Promise<HeadlessBody> {
  const text = await response.text()
  if (!text) return { status: response.status }

  let payload: unknown
  try {
    payload = JSON.parse(text)
  } catch {
    throw createHeadlessError(
      'The authentication service returned an invalid response.',
      { status: response.status },
    )
  }
  return headlessBody(payload, response.status)
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    throw createHeadlessError(
      'The authentication service returned an invalid response.',
      { status: response.status },
    )
  }
}

/**
 * Prime the browser's CSRF cookie using allauth's documented config endpoint.
 * The cookie itself is never persisted by this client.
 */
export async function bootstrapCsrf(): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${HEADLESS_BASE}/config`, { credentials: 'include' })
  } catch {
    throw createHeadlessError(
      'Could not initialize authentication security. Check your connection and try again.',
      { status: 0 },
    )
  }

  if (!response.ok) {
    throw createHeadlessError(
      `Could not initialize authentication security (HTTP ${response.status}).`,
      { status: response.status },
    )
  }
  if (!getCookie('csrftoken')) {
    throw createHeadlessError(
      'The authentication service did not set a CSRF cookie. Check that cookies are enabled.',
      { status: response.status },
    )
  }
}

async function csrfToken(): Promise<string> {
  const existing = getCookie('csrftoken')
  if (existing) return existing

  await bootstrapCsrf()
  const token = getCookie('csrftoken')
  if (!token) {
    throw createHeadlessError(
      'The authentication service did not set a CSRF cookie. Check that cookies are enabled.',
      { status: 0 },
    )
  }
  return token
}

/** Make a headless request, adding CSRF protection for every unsafe method. */
export async function headlessFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !headers.has('X-CSRFToken')) {
    headers.set('X-CSRFToken', await csrfToken())
  }

  try {
    return await fetch(`${HEADLESS_BASE}${path.startsWith('/') ? path : `/${path}`}`, {
      ...init,
      method,
      credentials: 'include',
      headers,
    })
  } catch {
    throw createHeadlessError(
      'Cannot reach the authentication service. Check your connection and try again.',
      { status: 0 },
    )
  }
}

async function requestBody(path: string, init: RequestInit = {}): Promise<HeadlessBody> {
  const response = await headlessFetch(path, init)
  return readBody(response)
}

function flowsFrom(body: HeadlessBody): HeadlessFlow[] {
  const flows = dataRecord(body)?.flows
  if (!Array.isArray(flows)) return []
  return flows.filter(
    (flow): flow is HeadlessFlow => isRecord(flow) && typeof flow.id === 'string',
  )
}

function pendingFlow(body: HeadlessBody): HeadlessFlow | undefined {
  return flowsFrom(body).find((flow) => flow.is_pending === true)
}

function isAnonymousSuccess(body: HeadlessBody): boolean {
  const data = dataRecord(body)
  return (
    body.status === 401 &&
    body.meta?.is_authenticated === false &&
    body.errors === undefined &&
    Array.isArray(data?.flows)
  )
}

/** Existing API: 200 means authenticated; 401 means anonymous or pending. */
export async function getSession(): Promise<HeadlessBody> {
  return requestBody('/auth/session')
}

/** Classify the actual allauth session response without inventing user fields. */
export async function getAuthenticationState(): Promise<AuthenticationState> {
  const body = await getSession()
  const flow = pendingFlow(body)

  if (body.status !== 200 && body.status !== 401) {
    throw createHeadlessError(
      firstErrorMessage(body, 'Could not verify the authentication session.'),
      body,
    )
  }
  if (body.meta?.is_authenticated === true) return { status: 'authenticated', body }
  if (flow) return { status: 'pending', flow, body }
  if (body.meta?.is_authenticated === false) return { status: 'anonymous', body }

  throw createHeadlessError(
    'The authentication service returned an invalid session response.',
    body,
  )
}

/** Fetch the authoritative dashboard profile after headless confirms a session. */
export async function getCurrentUser(): Promise<CurrentUser> {
  let response: Response
  try {
    response = await fetch('/api/auth/user/', { credentials: 'include' })
  } catch {
    throw createHeadlessError(
      'Cannot reach the dashboard account service. Check your connection and try again.',
      { status: 0 },
    )
  }

  const payload = await readJson(response)
  if (!response.ok) {
    const body = isRecord(payload) ? payload : {}
    const message =
      typeof body.detail === 'string'
        ? body.detail
        : response.status === 401
          ? 'Your dashboard session is no longer authenticated.'
          : `Could not load the dashboard profile (HTTP ${response.status}).`
    throw createHeadlessError(message, { status: response.status })
  }
  if (
    !isRecord(payload) ||
    typeof payload.id !== 'string' ||
    typeof payload.email !== 'string' ||
    typeof payload.username !== 'string' ||
    typeof payload.first_name !== 'string' ||
    typeof payload.last_name !== 'string' ||
    typeof payload.date_joined !== 'string' ||
    typeof payload.is_email_verified !== 'boolean' ||
    !Array.isArray(payload.memberships)
  ) {
    throw createHeadlessError(
      'The dashboard account service returned an invalid profile.',
      { status: response.status },
    )
  }

  const memberships: CurrentUser['memberships'] = []
  for (const membership of payload.memberships) {
    if (
      !isRecord(membership) ||
      typeof membership.organization !== 'string' ||
      typeof membership.role !== 'string'
    ) {
      throw createHeadlessError(
        'The dashboard account service returned an invalid profile.',
        { status: response.status },
      )
    }
    memberships.push({ organization: membership.organization, role: membership.role })
  }

  return {
    id: payload.id,
    email: payload.email,
    username: payload.username,
    first_name: payload.first_name,
    last_name: payload.last_name,
    date_joined: payload.date_joined,
    is_email_verified: payload.is_email_verified,
    memberships,
  }
}

export async function signIn(email: string, password: string): Promise<LoginResult> {
  const body = await requestBody('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })

  if (body.meta?.is_authenticated === true) return { kind: 'authenticated' }
  const flow = pendingFlow(body)
  if (flow?.id === 'mfa_authenticate') {
    return {
      kind: 'mfa',
      types: Array.isArray(flow.types)
        ? flow.types.filter((type): type is string => typeof type === 'string')
        : [],
    }
  }
  if (flow?.id === 'verify_email') return { kind: 'verify-email' }

  throw createHeadlessError(
    firstErrorMessage(body, 'Sign-in failed. Check your email and password.'),
    body,
  )
}

/** Sign up using only fields supported by main's allauth signup configuration. */
export async function signUp(input: {
  email: string
  password: string
}): Promise<LoginResult> {
  const body = await requestBody('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email: input.email, password: input.password }),
  })

  if (body.meta?.is_authenticated === true) return { kind: 'authenticated' }
  const flow = pendingFlow(body)
  if (flow?.id === 'verify_email') return { kind: 'verify-email' }
  if (flow?.id === 'mfa_authenticate') {
    return {
      kind: 'mfa',
      types: Array.isArray(flow.types)
        ? flow.types.filter((type): type is string => typeof type === 'string')
        : [],
    }
  }
  throw createHeadlessError(firstErrorMessage(body, 'Could not create the account.'), body)
}

export async function verifyEmail(key: string): Promise<void> {
  const body = await requestBody('/auth/email/verify', {
    method: 'POST',
    body: JSON.stringify({ key }),
  })
  if (body.status >= 200 && body.status < 300) return
  if (isAnonymousSuccess(body)) return
  throw createHeadlessError(
    firstErrorMessage(body, 'The email verification code is invalid or expired.'),
    body,
  )
}

export async function resendVerificationCode(): Promise<void> {
  const body = await requestBody('/auth/email/verify/resend', { method: 'POST' })
  if (body.status < 200 || body.status >= 300) {
    throw createHeadlessError(
      firstErrorMessage(body, 'Could not resend the email verification code.'),
      body,
    )
  }
}

export async function changeVerificationEmail(email: string): Promise<void> {
  const body = await requestBody('/account/email', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
  if (body.status < 200 || body.status >= 300) {
    throw createHeadlessError(
      firstErrorMessage(body, 'Could not change the verification email.'),
      body,
    )
  }
}

/** Request a reset email; allauth keeps unknown and known addresses indistinguishable. */
export async function requestPasswordReset(email: string): Promise<void> {
  const body = await requestBody('/auth/password/request', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
  if (body.status < 200 || body.status >= 300) {
    throw createHeadlessError(
      firstErrorMessage(body, 'Could not send the reset email.'),
      body,
    )
  }
}

/**
 * Confirm a password reset. Main's tested allauth response is 401 with
 * is_authenticated=false, no errors, and a flows array on successful reset.
 */
export async function confirmPasswordReset(key: string, password: string): Promise<void> {
  const body = await requestBody('/auth/password/reset', {
    method: 'POST',
    body: JSON.stringify({ key, password }),
  })
  if (body.status >= 200 && body.status < 300) return
  if (isAnonymousSuccess(body)) return
  throw createHeadlessError(
    firstErrorMessage(
      body,
      body.status === 429
        ? 'Too many reset attempts. Please wait a moment and try again.'
        : 'The password reset link is invalid or expired.',
    ),
    body,
  )
}

/** Change the password of the currently authenticated session user. */
export async function changePassword(current: string, next: string): Promise<void> {
  const body = await requestBody('/account/password/change', {
    method: 'POST',
    body: JSON.stringify({ current_password: current, new_password: next }),
  })
  if (body.status >= 200 && body.status < 300) return
  throw createHeadlessError(
    firstErrorMessage(
      body,
      body.status === 401
        ? 'You must be logged in to change the password.'
        : 'Could not change the password.',
    ),
    body,
  )
}

export async function signOut(): Promise<void> {
  const body = await requestBody('/auth/session', { method: 'DELETE' })
  if (body.status >= 200 && body.status < 300) return
  if (isAnonymousSuccess(body)) return
  throw createHeadlessError(firstErrorMessage(body, 'Sign-out failed.'), body)
}

export async function verifyMfa(code: string): Promise<void> {
  const body = await requestBody('/auth/2fa/authenticate', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
  if (body.status >= 200 && body.status < 300 && body.meta?.is_authenticated === true) return
  throw createHeadlessError(
    firstErrorMessage(body, 'The verification code was not accepted.'),
    body,
  )
}

export async function reauthenticate(password: string): Promise<void> {
  const body = await requestBody('/auth/reauthenticate', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })
  if (body.status >= 200 && body.status < 300) return
  throw createHeadlessError(
    firstErrorMessage(body, 'Could not verify the current password.'),
    body,
  )
}

export async function getAuthenticators(): Promise<unknown[]> {
  const body = await requestBody('/account/authenticators')
  if (body.status < 200 || body.status >= 300) {
    throw createHeadlessError(
      firstErrorMessage(body, 'Could not load authenticators.'),
      body,
    )
  }
  if (!Array.isArray(body.data)) {
    throw createHeadlessError(
      'The authentication service returned invalid authenticator data.',
      body,
    )
  }
  return body.data
}

export async function getTotpSetup(): Promise<{
  active: boolean
  secret?: string
  totpUrl?: string
}> {
  const body = await requestBody('/account/authenticators/totp')
  if (
    body.status === 404 &&
    typeof body.meta?.secret === 'string' &&
    typeof body.meta.totp_url === 'string'
  ) {
    return { active: false, secret: body.meta.secret, totpUrl: body.meta.totp_url }
  }
  if (body.status >= 200 && body.status < 300) return { active: true }
  throw createHeadlessError(
    firstErrorMessage(body, 'Could not load TOTP settings.'),
    body,
  )
}

export async function activateTotp(code: string): Promise<void> {
  const body = await requestBody('/account/authenticators/totp', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
  if (body.status < 200 || body.status >= 300) {
    throw createHeadlessError(
      firstErrorMessage(body, 'Could not enable TOTP authentication.'),
      body,
    )
  }
}

export async function removeTotp(): Promise<void> {
  const body = await requestBody('/account/authenticators/totp', { method: 'DELETE' })
  if (body.status < 200 || body.status >= 300) {
    throw createHeadlessError(
      firstErrorMessage(body, 'Could not remove TOTP authentication.'),
      body,
    )
  }
}

export async function generateRecoveryCodes(): Promise<string[]> {
  const body = await requestBody('/account/authenticators/recovery-codes', {
    method: 'POST',
    body: JSON.stringify({}),
  })
  if (body.status < 200 || body.status >= 300) {
    throw createHeadlessError(
      firstErrorMessage(body, 'Could not generate recovery codes.'),
      body,
    )
  }
  const data = dataRecord(body)
  const codes = data?.unused_codes
  if (!Array.isArray(codes)) {
    throw createHeadlessError('The authentication service did not return recovery codes.', body)
  }
  return codes.filter((code): code is string => typeof code === 'string')
}

export async function getRecoveryCodes(): Promise<string[] | null> {
  const body = await requestBody('/account/authenticators/recovery-codes')
  if (body.status === 404) return null
  if (body.status < 200 || body.status >= 300) {
    throw createHeadlessError(
      firstErrorMessage(body, 'Could not load recovery codes.'),
      body,
    )
  }
  const data = dataRecord(body)
  const codes = data?.unused_codes
  if (Array.isArray(codes)) {
    return codes.filter((code): code is string => typeof code === 'string')
  }
  if (typeof data?.unused_code_count === 'number') {
    return []
  }
  throw createHeadlessError(
    'The authentication service returned invalid recovery-code data.',
    body,
  )
}
