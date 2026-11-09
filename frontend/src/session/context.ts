import { createContext, useContext } from 'react'
import type { SpendRequest } from '../api/spendRequests'
import type { AuthStatus, LoginResult } from '../api/auth'

export interface Session {
  /** Kept in memory only: never written to storage or the URL. */
  agentKey: string
  setAgentKey: (key: string) => void
  /** Requests seen in this tab, newest first. Stands in until a list endpoint exists. */
  recent: SpendRequest[]
  remember: (request: SpendRequest) => void
  /** Authentication state restored from the backend on mount. */
  authenticated: boolean
  user: { username: string } | null
  setAuthenticated: (status: AuthStatus) => void
  /** Sign in with email/password. Returns the login result kind. */
  login: (email: string, password: string) => Promise<LoginResult>
  logout: () => Promise<void>
}

export const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('useSession must be used inside SessionProvider')
  return session
}
