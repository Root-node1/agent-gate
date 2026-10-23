import { Link } from 'react-router'
import { agentName, requestById } from '../../../demo/selectors'
import { RULE_INFO } from '../../../demo/rules'
import type { AuditEvent, DemoState } from '../../../demo/types'
import { describeEvent } from '../../../ui/events'
import { formatMoney, formatTimestamp, timeAgo } from '../../../ui/format'
import { DECISION, EVENT, type StatusLabel } from '../../../ui/labels'

const EVENT_ICON: Partial<Record<AuditEvent['event_type'], string>> = {
  'approval.requested': '⏳',
  'approval.approved': '✓',
  'approval.denied': '✕',
  'approval.expired': '⌛',
  'payment.completed': '✓',
  'payment.failed': '✕',
}

/** Tone, icon and headline for one feed item. */
function headline(state: DemoState, e: AuditEvent): StatusLabel {
  if (e.event_type === 'spend_request.decided') {
    const decision = requestById(state, e.spend_request_id)?.decision ?? 'pending'
    return DECISION[decision]
  }
  const info = EVENT[e.event_type]
  return { tone: info.tone, icon: EVENT_ICON[e.event_type] ?? '•', label: info.label }
}

/** Short explanation. For decisions, name the rule in plain words instead of listing rule codes. */
function explain(state: DemoState, e: AuditEvent): string {
  if (e.event_type !== 'spend_request.decided') return describeEvent(state, e)
  const rules = (e.payload.rules as string[] | undefined) ?? []
  if (rules.length === 0) return 'Passed every rule.'
  // Hard rules first: they are the reason it was blocked.
  const sorted = [...rules].sort((a, b) => Number(RULE_INFO[b]?.outcome === 'deny') - Number(RULE_INFO[a]?.outcome === 'deny'))
  const first = RULE_INFO[sorted[0]]?.label ?? sorted[0]
  return sorted.length > 1 ? `${first}, plus ${sorted.length - 1} more.` : `${first}.`
}

interface Props {
  state: DemoState
  events: AuditEvent[]
  now: number
  /** Events with a higher id arrived after the page opened and get an entrance animation. */
  newerThan: number
}

export default function ActivityFeed({ state, events, now, newerThan }: Props) {
  return (
    <ol className="ov-feed">
      {events.map((e) => {
        const request = requestById(state, e.spend_request_id)
        const head = headline(state, e)
        const to = request ? `/app/transactions/${request.id}` : `/app/audit?event=${e.id}`
        return (
          <li key={e.id} className={`ov-feed-item${e.id > newerThan ? ' ov-feed-new' : ''}`}>
            <span className={`ov-feed-dot tone-${head.tone}`} aria-hidden="true">
              {head.icon}
            </span>
            <div className="ov-feed-body">
              <div className="ov-feed-top">
                <Link to={to} className="ov-feed-link">
                  {head.label}
                  {request && (
                    <span className="ov-feed-amount">
                      {' · '}
                      {formatMoney(request.amount, request.currency)} to {request.merchant}
                    </span>
                  )}
                </Link>
                <time dateTime={e.created_at} title={formatTimestamp(e.created_at)} className="ov-feed-time">
                  {timeAgo(e.created_at, now)}
                </time>
              </div>
              <p className="ov-feed-text">
                <span className="ov-feed-agent">{agentName(state, e.agent_id)}</span> · {explain(state, e)}
              </p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
