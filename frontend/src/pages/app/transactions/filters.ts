import type { Decision, PaymentStatus, SpendRequest } from '../../../demo/types'
import { DECISION, PAYMENT } from '../../../ui/labels'

export type Range = 'today' | '7d' | '14d' | 'all'

export const RANGES: { value: Range; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: '7d', label: '7 days' },
  { value: '14d', label: '14 days' },
  { value: 'all', label: 'All' },
]

export const PAGE_SIZE = 25

export interface Filters {
  agent: string
  decision: Decision | ''
  payment: PaymentStatus | ''
  range: Range
  q: string
}

/** Read filters from the URL, ignoring values we do not know. */
export function readFilters(params: URLSearchParams): Filters {
  const decision = params.get('decision') ?? ''
  const payment = params.get('payment') ?? ''
  const range = params.get('range') ?? 'all'
  return {
    agent: params.get('agent') ?? '',
    decision: decision in DECISION ? (decision as Decision) : '',
    payment: payment in PAYMENT ? (payment as PaymentStatus) : '',
    range: RANGES.some((r) => r.value === range) ? (range as Range) : 'all',
    q: params.get('q') ?? '',
  }
}

export function hasFilters(f: Filters): boolean {
  return Boolean(f.agent || f.decision || f.payment || f.q.trim() || f.range !== 'all')
}

function rangeStart(range: Range, now: Date): Date | null {
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  if (range === 'today') return midnight
  if (range === '7d') return new Date(midnight.getFullYear(), midnight.getMonth(), midnight.getDate() - 6)
  if (range === '14d') return new Date(midnight.getFullYear(), midnight.getMonth(), midnight.getDate() - 13)
  return null
}

export function applyFilters(requests: SpendRequest[], f: Filters, now = new Date()): SpendRequest[] {
  const since = rangeStart(f.range, now)
  const q = f.q.trim().toLowerCase()
  return requests.filter((r) => {
    if (f.agent && String(r.agent_id) !== f.agent) return false
    if (f.decision && r.decision !== f.decision) return false
    if (f.payment && r.payment_status !== f.payment) return false
    if (since && new Date(r.created_at) < since) return false
    if (q && !r.merchant.toLowerCase().includes(q) && !r.id.toLowerCase().startsWith(q)) return false
    return true
  })
}
