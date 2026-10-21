import type { AuditEvent, AuditEventType } from '../../../demo/types'

/** The overview summarises the same window the chart shows. */
export const WINDOW_DAYS = 14

/** Local midnight at the start of the window (today counts as day 1). */
export function windowStart(now: number, days = WINDOW_DAYS): Date {
  const d = new Date(now)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - (days - 1))
}

/** "3 hours", "12 minutes", "2 days": how long something has been waiting. */
export function duration(fromIso: string, now: number): string {
  const minutes = Math.max(0, Math.round((now - new Date(fromIso).getTime()) / 60_000))
  if (minutes < 1) return 'less than a minute'
  if (minutes < 60) return plural(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (hours < 24) return plural(hours, 'hour')
  return plural(Math.round(hours / 24), 'day')
}

export function plural(n: number, word: string): string {
  return `${n.toLocaleString()} ${word}${n === 1 ? '' : 's'}`
}

/**
 * Spend-request events worth showing in the live feed. "Received" and
 * "approval requested" are skipped: the decision event right after says the same.
 */
const FEED_TYPES = new Set<AuditEventType>([
  'spend_request.decided',
  'approval.approved',
  'approval.denied',
  'approval.expired',
  'payment.completed',
  'payment.failed',
])

export function feedEvents(events: AuditEvent[], limit: number): AuditEvent[] {
  const result: AuditEvent[] = []
  for (const e of events) {
    if (!FEED_TYPES.has(e.event_type)) continue
    result.push(e)
    if (result.length === limit) break
  }
  return result
}

/** A rounded axis maximum and its ticks (0 included), e.g. 7 -> [0, 2, 4, 6, 8]. */
export function niceTicks(max: number, target = 4): number[] {
  if (max <= 0) return [0, 1]
  const rough = max / target
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? magnitude * 10
  const stepInt = Math.max(1, Math.round(step))
  const ticks: number[] = []
  for (let t = 0; t < max + stepInt; t += stepInt) ticks.push(t)
  return ticks
}

/** "Oct 8" from a local YYYY-MM-DD key. */
export function shortDay(key: string): string {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function longDay(key: string): string {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
}
