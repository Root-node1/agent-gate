import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { SpendRequest } from '../api/spendRequests'
import {
  getAuthStatus,
  signIn,
  signOut,
  type AuthStatus,
  type LoginResult,
} from '../api/auth'
import { SessionContext } from './context'

const MAX_RECENT = 20

export default function SessionProvider({ children }: { children: ReactNode }) {
  const [agentKey, setAgentKey] = useState('')
  const [recent, setRecent] = useState<SpendRequest[]>([])
  const [authenticated, setAuthenticated] = useState(false)
  const [user, setUser] = useState<{ username: string } | null>(null)

  const remember = useCallback((request: SpendRequest) => {
    setRecent((prev) => {
      const index = prev.findIndex((r) => r.id === request.id)
      if (index !== -1) return prev.map((r, i) => (i === index ? request : r))
      return [request, ...prev].slice(0, MAX_RECENT)
    })
  }, [])

  const setAuthStatus = useCallback((status: AuthStatus) => {
    if (status.authenticated) {
      setAuthenticated(true)
      setUser(status.user)
    } else {
      setAuthenticated(false)
      setUser(null)
    }
  }, [])

  // Restore session from backend on mount.
  useEffect(() => {
    let mounted = true
    getAuthStatus()
      .then((status) => {
        if (mounted) setAuthStatus(status)
      })
      .catch(() => {
        if (mounted) setAuthStatus({ authenticated: false })
      })
    return () => {
      mounted = false
    }
  }, [setAuthStatus])

  const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
    const result = await signIn(email, password)
    if (result.kind === 'authenticated') {
      setAuthStatus({ authenticated: true, user: { username: email } })
    }
    return result
  }, [setAuthStatus])

  const logout = useCallback(async () => {
    try {
      await signOut()
    } catch {
      // Ignore sign-out errors; always clear local state.
    }
    setAuthenticated(false)
    setUser(null)
    window.location.replace('/login')
  }, [])

  const value = useMemo(
    () => ({
      agentKey,
      setAgentKey,
      recent,
      remember,
      authenticated,
      user,
      setAuthenticated: setAuthStatus,
      login,
      logout,
    }),
    [agentKey, recent, remember, authenticated, user, setAuthStatus, login, logout],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
