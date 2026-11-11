import { useEffect, useState } from 'react'

export type ApiResourceState<T> =
  | { status: 'loading' }
  | { status: 'empty'; data: T }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error }

function isEmptyResult(value: unknown): boolean {
  if (Array.isArray(value)) return value.length === 0
  if (
    typeof value === 'object' &&
    value !== null &&
    'results' in value &&
    Array.isArray(value.results)
  ) {
    return value.results.length === 0
  }
  return false
}

/** Recreate `load` with useCallback when its inputs change. */
export function useApiResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
): ApiResourceState<T> {
  const [state, setState] = useState<ApiResourceState<T>>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    load(controller.signal).then(
      (data) => {
        if (active) {
          setState(isEmptyResult(data) ? { status: 'empty', data } : { status: 'success', data })
        }
      },
      (error: unknown) => {
        if (active && !controller.signal.aborted) {
          setState({
            status: 'error',
            error: error instanceof Error ? error : new Error('The request failed.'),
          })
        }
      },
    )

    return () => {
      active = false
      controller.abort()
    }
  }, [load])

  return state
}
