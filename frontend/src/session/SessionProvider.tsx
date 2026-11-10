import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  getAuthenticationState,
  getCurrentUser,
  signIn,
  signUp,
  signOut,
  type CurrentUser,
  type HeadlessFlow,
} from '../api/auth'
import type { SpendRequest } from '../api/spendRequests'
import { SessionContext } from './context'
import {
  pendingAuthenticationFlow,
  resolveSession,
  type SessionResolution,
} from './sessionModel'

const MAX_RECENT = 20

type AuthenticationStatus =
  | 'loading'
  | 'authenticated'
  | 'unauthenticated'
  | 'pending'
  | 'error'

export default function SessionProvider({ children }: { children: ReactNode }) {
  const [agentKey, setAgentKey] = useState('')
  const [recent, setRecent] = useState<SpendRequest[]>([])
  const [authenticationStatus, setAuthenticationStatus] =
    useState<AuthenticationStatus>('loading')
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [pendingFlow, setPendingFlow] = useState<HeadlessFlow | null>(null)
  const [authenticationError, setAuthenticationError] = useState<string | null>(null)
  const requestId = useRef(0)
  const initialRequest = useRef<Promise<SessionResolution> | null>(null)

  const refreshSession = useCallback(async () => {
    const id = ++requestId.current
    setAuthenticationError(null)
    setAuthenticationStatus('loading')
    try {
      const session = await resolveSession(getAuthenticationState, getCurrentUser)
      if (requestId.current === id) {
        setCurrentUser(session.status === 'authenticated' ? session.user : null)
        setPendingFlow(session.status === 'pending' ? session.flow : null)
        setAuthenticationStatus(session.status)
      } else {
        throw new Error('Session verification was superseded by a newer authentication action.')
      }
      return session
    } catch (error) {
      if (requestId.current === id) {
        setCurrentUser(null)
        setPendingFlow(null)
        setAuthenticationStatus('error')
        setAuthenticationError(
          error instanceof Error ? error.message : 'Could not verify the dashboard session.',
        )
      }
      throw error
    }
  }, [])

  useEffect(() => {
    let request = initialRequest.current
    if (!request) {
      request = refreshSession().finally(() => {
        initialRequest.current = null
      })
      initialRequest.current = request
    }
    void request.catch(() => undefined)
  }, [refreshSession])

  const login = useCallback(async (email: string, password: string) => {
    setAuthenticationError(null)
    const result = await signIn(email, password)
    if (result.kind === 'authenticated') {
      const session = await refreshSession()
      if (session.status !== 'authenticated') {
        throw new Error('Sign-in was not confirmed by the dashboard session.')
      }
    } else {
      setCurrentUser(null)
      const flow = pendingAuthenticationFlow(result)
      setPendingFlow(flow)
      setAuthenticationStatus(flow ? 'pending' : 'unauthenticated')
    }
    return result
  }, [refreshSession])

  const register = useCallback(async (email: string, password: string) => {
    setAuthenticationError(null)
    const result = await signUp({ email, password })
    if (result.kind === 'authenticated') {
      const session = await refreshSession()
      if (session.status !== 'authenticated') {
        throw new Error('Account creation was not confirmed by the dashboard session.')
      }
    } else {
      setCurrentUser(null)
      const flow = pendingAuthenticationFlow(result)
      setPendingFlow(flow)
      setAuthenticationStatus(flow ? 'pending' : 'unauthenticated')
    }
    return result
  }, [refreshSession])

  const logout = useCallback(async () => {
    setAuthenticationError(null)
    try {
      await signOut()
      requestId.current += 1
      setCurrentUser(null)
      setPendingFlow(null)
      setAuthenticationStatus('unauthenticated')
    } catch (error) {
      setAuthenticationError(
        error instanceof Error ? error.message : 'Sign-out failed. Please try again.',
      )
      throw error
    }
  }, [])

  const remember = useCallback((request: SpendRequest) => {
    setRecent((prev) => {
      const index = prev.findIndex((r) => r.id === request.id)
      if (index !== -1) return prev.map((r, i) => (i === index ? request : r))
      return [request, ...prev].slice(0, MAX_RECENT)
    })
  }, [])

  const value = useMemo(
    () => ({
      agentKey,
      setAgentKey,
      recent,
      remember,
      authenticationStatus,
      currentUser,
      pendingFlow,
      authenticationError,
      refreshSession,
      login,
      register,
      logout,
    }),
    [
      agentKey,
      recent,
      remember,
      authenticationStatus,
      currentUser,
      pendingFlow,
      authenticationError,
      refreshSession,
      login,
      register,
      logout,
    ],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
