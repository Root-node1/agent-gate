import { useEffect, useState } from 'react'

/**
 * True for a short moment after mount. The demo store answers instantly, so
 * this gives screens a realistic loading state to show (skeletons) and keeps
 * the loading UI exercised until real API calls replace the store.
 */
export function useSimulatedLoad(ms = 450): boolean {
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), ms)
    return () => clearTimeout(timer)
  }, [ms])
  return loading
}

/** Current time, refreshed every `ms`, so "5 minutes ago" labels stay correct. */
export function useNow(ms = 30_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(timer)
  }, [ms])
  return now
}
