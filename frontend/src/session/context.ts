import { createContext, useContext } from 'react'
import type { SpendRequest } from '../api/spendRequests'

export interface Session {
  /** Kept in memory only: never written to storage or the URL. */
  agentKey: string
  setAgentKey: (key: string) => void
  /** Requests seen in this tab, newest first. Stands in until a list endpoint exists. */
  recent: SpendRequest[]
  remember: (request: SpendRequest) => void
}

export const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('useSession must be used inside SessionProvider')
  return session
}
