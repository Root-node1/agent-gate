export class CsrfBootstrapError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'CsrfBootstrapError'
    this.status = status
  }
}

/**
 * Production API base URL — mirrors the value in client.ts.
 * When unset, CSRF bootstrap uses relative paths (local dev proxy).
 *
 * import.meta.env is only available in Vite builds. In Node.js test
 * environments it is undefined, so we guard against that case.
 */
const API_BASE = ((typeof import.meta !== 'undefined'
  ? import.meta.env?.VITE_API_BASE_URL
  : undefined) as string | undefined)?.replace(/\/+$/, '') ?? ''

function csrfCookie(): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : null
}

function csrfPath() {
  return API_BASE ? `${API_BASE}/api/auth/csrf/` : '/api/auth/csrf/'
}

export async function bootstrapCsrfCookie(): Promise<string> {
  let response: Response
  try {
    response = await fetch(csrfPath(), {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new CsrfBootstrapError(
      'Could not initialize request security. Check your connection and try again.',
      0,
    )
  }

  if (!response.ok) {
    throw new CsrfBootstrapError(
      `Could not initialize request security (HTTP ${response.status}).`,
      response.status,
    )
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new CsrfBootstrapError(
      'The authentication service returned an invalid CSRF response.',
      response.status,
    )
  }
  if (
    typeof payload !== 'object' ||
    payload === null ||
    !('csrfToken' in payload) ||
    typeof payload.csrfToken !== 'string'
  ) {
    throw new CsrfBootstrapError(
      'The authentication service returned an invalid CSRF response.',
      response.status,
    )
  }

  const cookie = csrfCookie()
  if (!cookie) {
    throw new CsrfBootstrapError(
      'The authentication service did not set a CSRF cookie. Check that cookies are enabled.',
      response.status,
    )
  }
  return cookie
}

export async function getCsrfToken(): Promise<string> {
  return csrfCookie() ?? bootstrapCsrfCookie()
}
