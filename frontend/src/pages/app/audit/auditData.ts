import { agentName, requestById } from '../../../demo/selectors'
import type { AuditEvent, AuditEventType, Decision, DemoState, SpendRequest } from '../../../demo/types'
import { describeEvent } from '../../../ui/events'
import { EVENT, EVENT_GROUPS } from '../../../ui/labels'

export type ActorKind = 'person' | 'agent' | 'system'

export const ACTOR_KIND_LABEL: Record<ActorKind, string> = {
  person: 'Person',
  agent: 'Agent',
  system: 'System',
}

/** URL value for the actor filter, plural for readability in the select. */
export const ACTOR_FILTERS: { value: ActorKind; label: string }[] = [
  { value: 'person', label: 'People' },
  { value: 'agent', label: 'Agents' },
  { value: 'system', label: 'System (AgentGate, PayPal)' },
]

export const PAGE_SIZE = 25

const SYSTEM_ACTORS = new Set(['AgentGate', 'PayPal'])

export function actorKind(actor: string): ActorKind {
  if (SYSTEM_ACTORS.has(actor)) return 'system'
  if (actor.includes('@')) return 'person'
  return 'agent'
}

export interface AuditRow {
  event: AuditEvent
  request: SpendRequest | undefined
  agent: string
  kind: ActorKind
  explanation: string
  decision: Decision | null
  /** Lowercased text the search box matches against. */
  haystack: string
}

export function buildRows(s: DemoState): AuditRow[] {
  return s.events.map((event) => {
    const request = requestById(s, event.spend_request_id)
    const agent = event.agent_id === null ? '' : agentName(s, event.agent_id)
    const explanation = describeEvent(s, event)
    const decision =
      request?.decision ?? ((event.payload.decision as Decision | undefined) || null)
    const haystack = [
      explanation,
      event.actor,
      agent,
      EVENT[event.event_type].label,
      event.event_type,
      request?.merchant ?? (event.payload.merchant as string | undefined) ?? '',
      request?.purpose ?? '',
      request?.paypal_reference ?? '',
      event.spend_request_id ?? '',
      String(event.id),
    ]
      .join(' ')
      .toLowerCase()
    return { event, request, agent, kind: actorKind(event.actor), explanation, decision, haystack }
  })
}

export interface AuditFilters {
  q: string
  /** An event type, or "group:<index>" for a whole group. */
  type: string
  agent: string
  actor: string
  from: string
  to: string
}

export function readFilters(params: URLSearchParams): AuditFilters {
  return {
    q: params.get('q') ?? '',
    type: params.get('type') ?? '',
    agent: params.get('agent') ?? '',
    actor: params.get('actor') ?? '',
    from: params.get('from') ?? '',
    to: params.get('to') ?? '',
  }
}

export function hasFilters(f: AuditFilters): boolean {
  return Object.values(f).some(Boolean)
}

function typesFor(type: string): Set<AuditEventType> | null {
  if (!type) return null
  if (type.startsWith('group:')) {
    const group = EVENT_GROUPS[Number(type.slice(6))]
    return new Set(group?.types ?? [])
  }
  return new Set([type as AuditEventType])
}

function localDateKey(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function applyFilters(rows: AuditRow[], f: AuditFilters): AuditRow[] {
  const terms = f.q.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const types = typesFor(f.type)
  return rows.filter((row) => {
    const e = row.event
    if (types && !types.has(e.event_type)) return false
    if (f.agent && String(e.agent_id) !== f.agent) return false
    if (f.actor && row.kind !== f.actor) return false
    if (f.from || f.to) {
      const day = localDateKey(e.created_at)
      if (f.from && day < f.from) return false
      if (f.to && day > f.to) return false
    }
    return terms.every((t) => row.haystack.includes(t))
  })
}

function csvCell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
}

export function toCsv(rows: AuditRow[]): string {
  const header = [
    'event_id',
    'timestamp',
    'event_type',
    'event',
    'actor',
    'actor_kind',
    'agent',
    'decision',
    'spend_request_id',
    'explanation',
    'payload',
  ]
  const lines = rows.map((r) =>
    [
      String(r.event.id),
      r.event.created_at,
      r.event.event_type,
      EVENT[r.event.event_type].label,
      r.event.actor,
      r.kind,
      r.agent,
      r.decision ?? '',
      r.event.spend_request_id ?? '',
      r.explanation,
      JSON.stringify(r.event.payload),
    ]
      .map(csvCell)
      .join(','),
  )
  return [header.join(','), ...lines].join('\r\n')
}

export function downloadCsv(filename: string, csv: string) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** "21 Oct 2026": first line of the table's time cell. */
export function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

/** "16:48:56": second line, with seconds for audit precision. */
export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
