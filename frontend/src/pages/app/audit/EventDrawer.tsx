import { Link } from 'react-router'
import { agentById, approvalForRequest, requestById, timelineForRequest } from '../../../demo/selectors'
import type { AuditEvent, DemoState } from '../../../demo/types'
import EmptyState from '../../../ui/EmptyState'
import Modal from '../../../ui/Modal'
import ReasonList from '../../../ui/ReasonList'
import { ApprovalStatus, DecisionStatus, PaymentStatusBadge } from '../../../ui/StatusBadges'
import Timeline from '../../../ui/Timeline'
import { describeEvent } from '../../../ui/events'
import { formatDateTime, formatMoney, formatTimestamp, timeAgo } from '../../../ui/format'
import { EVENT } from '../../../ui/labels'
import ActorLabel from './ActorLabel'
import EventType from './EventType'

interface Props {
  state: DemoState
  /** The id from the URL; null when the drawer is closed. */
  eventId: string | null
  onClose: () => void
}

export default function EventDrawer({ state, eventId, onClose }: Props) {
  const event = eventId === null ? undefined : state.events.find((e) => String(e.id) === eventId)
  const title = event ? EVENT[event.event_type].label : 'Event not found'
  return (
    <Modal
      open={eventId !== null}
      onClose={onClose}
      kind="drawer"
      title={title}
      footer={
        <>
          {event?.spend_request_id && (
            <Link to={`/app/transactions/${event.spend_request_id}`} className="btn btn-secondary">
              Open transaction
            </Link>
          )}
          <button type="button" className="btn btn-primary" onClick={onClose}>
            Close
          </button>
        </>
      }
    >
      {event ? (
        <EventDetail state={state} event={event} />
      ) : (
        <EmptyState title={`We couldn't find event #${eventId}`}>
          The link may be wrong, or the demo was reset since it was shared.
        </EmptyState>
      )}
    </Modal>
  )
}

function noReviewText(decision: string) {
  if (decision === 'allow') return 'No person needed: it passed every rule, so AgentGate allowed it automatically.'
  if (decision === 'deny') return 'No person needed: it broke a hard rule, so AgentGate blocked it automatically.'
  return 'No human review recorded.'
}

function EventDetail({ state, event }: { state: DemoState; event: AuditEvent }) {
  const agent = agentById(state, event.agent_id)
  const requestId = event.spend_request_id
  const request = requestById(state, requestId)
  const approval = request ? approvalForRequest(state, request.id) : undefined

  return (
    <div className="stack-lg au-drawer">
      <p className="au-drawer-summary">{describeEvent(state, event)}</p>

      <dl className="kv">
        <dt>Event</dt>
        <dd className="cluster">
          <EventType type={event.event_type} />
          <code className="small">{event.event_type}</code>
        </dd>
        <dt>Event ID</dt>
        <dd className="mono">#{event.id}</dd>
        <dt>Time</dt>
        <dd>
          <time dateTime={event.created_at}>{formatTimestamp(event.created_at)}</time>{' '}
          <span className="muted">({timeAgo(event.created_at)})</span>
        </dd>
        <dt>Actor</dt>
        <dd>
          <ActorLabel actor={event.actor} />
        </dd>
        <dt>Agent</dt>
        <dd>{agent ? <Link to={`/app/agents/${agent.id}`}>{agent.name}</Link> : '—'}</dd>
        {requestId && (
          <>
            <dt>Request</dt>
            <dd>
              <Link to={`/app/transactions/${requestId}`} className="mono">
                {requestId}
              </Link>
            </dd>
          </>
        )}
      </dl>

      {request && (
        <>
          <section className="stack au-section" aria-labelledby="au-request-heading">
            <h3 id="au-request-heading" className="au-section-title">
              The request
            </h3>
            <dl className="kv">
              <dt>Amount</dt>
              <dd>{formatMoney(request.amount, request.currency)}</dd>
              <dt>Merchant</dt>
              <dd>{request.merchant}</dd>
              <dt>Purpose</dt>
              <dd>{request.purpose}</dd>
              <dt>Decision</dt>
              <dd>
                <DecisionStatus decision={request.decision} />
              </dd>
            </dl>
          </section>

          <section className="stack au-section" aria-labelledby="au-why-heading">
            <h3 id="au-why-heading" className="au-section-title">
              Why AgentGate decided this
            </h3>
            <ReasonList reasons={request.reasons} />
          </section>

          <section className="stack au-section" aria-labelledby="au-who-heading">
            <h3 id="au-who-heading" className="au-section-title">
              Who authorized it
            </h3>
            {approval ? (
              <dl className="kv">
                <dt>Review</dt>
                <dd>
                  <ApprovalStatus outcome={approval.outcome} />
                </dd>
                <dt>Decided by</dt>
                <dd>
                  {approval.approver ? (
                    <ActorLabel actor={approval.approver} />
                  ) : approval.outcome === 'pending' ? (
                    'Waiting for a person'
                  ) : (
                    'Nobody, it expired'
                  )}
                </dd>
                {approval.decided_at && (
                  <>
                    <dt>Decided at</dt>
                    <dd>{formatTimestamp(approval.decided_at)}</dd>
                  </>
                )}
                {approval.outcome === 'pending' && (
                  <>
                    <dt>Expires</dt>
                    <dd>{formatDateTime(approval.expires_at)}</dd>
                  </>
                )}
                <dt>Note</dt>
                <dd>{approval.note ? `“${approval.note}”` : <span className="muted">No note</span>}</dd>
              </dl>
            ) : (
              <p className="hint">{noReviewText(request.decision)}</p>
            )}
          </section>

          <section className="stack au-section" aria-labelledby="au-payment-heading">
            <h3 id="au-payment-heading" className="au-section-title">
              Payment outcome
            </h3>
            <dl className="kv">
              <dt>Status</dt>
              <dd>
                <PaymentStatusBadge status={request.payment_status} />
              </dd>
              <dt>PayPal reference</dt>
              <dd className="mono">{request.paypal_reference || <span className="muted">None</span>}</dd>
            </dl>
          </section>

          <section className="stack au-section" aria-labelledby="au-timeline-heading">
            <h3 id="au-timeline-heading" className="au-section-title">
              Full timeline
            </h3>
            <Timeline state={state} events={timelineForRequest(state, request.id)} />
          </section>
        </>
      )}

      <section className="stack au-section" aria-labelledby="au-raw-heading">
        <h3 id="au-raw-heading" className="au-section-title">
          Raw payload
        </h3>
        <pre className="au-json" tabIndex={0} aria-label="Event payload as JSON">
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      </section>
    </div>
  )
}
