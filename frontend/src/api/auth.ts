export interface AuthUser {
  username: string
}

export type AuthStatus =
  | { authenticated: false }
  | { authenticated: true; user: AuthUser }

export class AuthError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function responseBody(response: Response): Promise<Record<string, unknown>> {
  const body: unknown = await response.json().catch(() => ({}))
  return isRecord(body) ? body : {}
}

async function csrfToken(): Promise<string> {
  const response = await fetch('/api/auth/csrf/', { credentials: 'same-origin' })
  const body = await responseBody(response)
  if (!response.ok || typeof body.csrfToken !== 'string') {
    throw new AuthError('Could not prepare a secure sign-in request.', response.status)
  }
  return body.csrfToken
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

export async function signIn(username: string, password: string): Promise<AuthUser> {
  const token = await csrfToken()
  const response = await fetch('/api/auth/login/', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': token,
    },
    body: JSON.stringify({ username, password }),
  })
  const body = await responseBody(response)
  if (!response.ok) {
    throw new AuthError(
      typeof body.detail === 'string' ? body.detail : 'Sign-in failed.',
      response.status,
    )
  }
  if (
    body.authenticated === true &&
    isRecord(body.user) &&
    typeof body.user.username === 'string'
  ) {
    return { username: body.user.username }
  }
  throw new AuthError('The backend returned an invalid sign-in response.', response.status)
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
