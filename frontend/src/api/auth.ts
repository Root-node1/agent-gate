/**
 * Minimal client for the allauth Headless browser JSON contract.
 *
 * Unlike the agent-key path (which uses a Bearer token), dashboard-user auth is
 * session-cookie based. Every request carries `credentials: "include"` and a
 * CSRF token read from the `csrftoken` cookie. The first GET to a headless
 * endpoint (e.g. `/config`) primes that cookie via allauth's `get_token()`.
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
