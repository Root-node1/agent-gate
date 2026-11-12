export type UUID = string
export type IsoDateTime = string

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface ListOptions {
  limit?: number
  offset?: number
  signal?: AbortSignal
}

export function pageQuery(options: ListOptions = {}): string {
  const query = new URLSearchParams()
  if (options.limit !== undefined) query.set('limit', String(options.limit))
  if (options.offset !== undefined) query.set('offset', String(options.offset))
  const value = query.toString()
  return value ? `?${value}` : ''
}
