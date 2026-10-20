import { useCallback, useMemo, useState, type ReactNode } from 'react'
import type { SpendRequest } from '../api/spendRequests'
import { SessionContext } from './context'

const MAX_RECENT = 20

export default function SessionProvider({ children }: { children: ReactNode }) {
  const [agentKey, setAgentKey] = useState('')
  const [recent, setRecent] = useState<SpendRequest[]>([])

  const remember = useCallback((request: SpendRequest) => {
    setRecent((prev) => {
      const index = prev.findIndex((r) => r.id === request.id)
      if (index !== -1) return prev.map((r, i) => (i === index ? request : r))
      return [request, ...prev].slice(0, MAX_RECENT)
    })
  }, [])

  const value = useMemo(
    () => ({ agentKey, setAgentKey, recent, remember }),
    [agentKey, recent, remember],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
