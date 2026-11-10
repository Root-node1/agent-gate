import { createContext, useContext } from 'react'
import type { CurrentUser, HeadlessFlow, LoginResult } from '../api/auth'
import type { SpendRequest } from '../api/spendRequests'
import type { SessionResolution } from './sessionModel'

export type AuthenticationStatus =
  | 'loading'
  | 'authenticated'
  | 'unauthenticated'
  | 'pending'
  | 'error'

export interface Session {
  /** Kept in memory only: never written to storage or the URL. */
  agentKey: string
  setAgentKey: (key: string) => void
  /** Requests seen in this tab, newest first. Stands in until a list endpoint exists. */
  recent: SpendRequest[]
  remember: (request: SpendRequest) => void
  authenticationStatus: AuthenticationStatus
  currentUser: CurrentUser | null
  pendingFlow: HeadlessFlow | null
  authenticationError: string | null
  refreshSession: () => Promise<SessionResolution>
  login: (email: string, password: string) => Promise<LoginResult>
  register: (email: string, password: string) => Promise<LoginResult>
  logout: () => Promise<void>
}

export const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('useSession must be used inside SessionProvider')
  return session
}
