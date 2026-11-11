import { useSession } from '../session/context'

/**
 * Determine whether the dashboard should query real backend APIs
 * or render the in-memory demo fixtures.
 *
 * When an authenticated user has an active organization membership,
 * data access operates in real API mode.
 */
export function useIsLiveApi(): boolean {
  const { currentUser, authenticationStatus } = useSession()
  return authenticationStatus === 'authenticated' && Boolean(currentUser?.memberships?.length)
}
