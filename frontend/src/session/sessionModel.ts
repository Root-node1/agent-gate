import type {
  AuthenticationState,
  CurrentUser,
  HeadlessFlow,
  LoginResult,
} from '../api/auth'

export type SessionResolution =
  | { status: 'authenticated'; user: CurrentUser }
  | { status: 'unauthenticated' }
  | { status: 'pending'; flow: HeadlessFlow }

export function pendingAuthenticationPath(flow: HeadlessFlow): '/mfa' | '/verify-email' | null {
  if (flow.id === 'mfa_authenticate') return '/mfa'
  if (flow.id === 'verify_email') return '/verify-email'
  return null
}

export function pendingAuthenticationFlow(result: LoginResult): HeadlessFlow | null {
  if (result.kind === 'mfa') {
    return { id: 'mfa_authenticate', is_pending: true, types: result.types }
  }
  if (result.kind === 'verify-email') {
    return { id: 'verify_email', is_pending: true }
  }
  return null
}

export async function resolveSession(
  getAuthenticationState: () => Promise<AuthenticationState>,
  getCurrentUser: () => Promise<CurrentUser>,
): Promise<SessionResolution> {
  const authentication = await getAuthenticationState()
  if (authentication.status === 'anonymous') return { status: 'unauthenticated' }
  if (authentication.status === 'pending') {
    return { status: 'pending', flow: authentication.flow }
  }
  return { status: 'authenticated', user: await getCurrentUser() }
}
