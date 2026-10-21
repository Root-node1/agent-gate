import { Link, useParams } from 'react-router'
import { FileQuestion } from 'lucide-react'
import { useDemoState } from '../../demo/store'
import {
  agentById,
  approvalForRequest,
  requestById,
  riskIndicators,
  timelineForRequest,
} from '../../demo/selectors'
import CopyField from '../../ui/CopyField'
import EmptyState from '../../ui/EmptyState'
import PageHeader from '../../ui/PageHeader'
import ReasonList, { RiskList } from '../../ui/ReasonList'
import { ApprovalStatus, DecisionStatus, PaymentStatusBadge } from '../../ui/StatusBadges'
import Timeline from '../../ui/Timeline'
import { formatDateTime, formatMoney, formatTimestamp, timeAgo } from '../../ui/format'
import { useNow } from '../../ui/hooks'
import { DECISION, SOURCE } from '../../ui/labels'
import { explainDecision, explainPayment } from './transactions/explain'
import './TransactionsPage.css'

const HEADINGS = {
  allow: 'Why it was allowed',
  deny: 'Why it was denied',
  needs_approval: 'Why it needs a person',
  pending: 'Decision',
}

export default function TransactionDetailPage() {
  const { id = '' } = useParams()
  const state = useDemoState()
  const now = useNow()
  const request = requestById(state, id)

  if (!request) {
    return (
      <>
        <PageHeader title="Request not found" back={{ to: '/app/transactions', label: 'Transactions' }} />
        <div className="card">
          <EmptyState
            icon={<FileQuestion size={22} />}
            title="We couldn't find this payment request"
            action={
              <Link to="/app/transactions" className="btn btn-primary">
                Back to transactions
              </Link>
            }
          >
            The link may be wrong, or the demo was reset and the request no longer exists.
          </EmptyState>
        </div>
      </>
    )
  }

  const agent = agentById(state, request.agent_id)
  const name = agent?.name ?? 'Unknown agent'
  const approval = approvalForRequest(state, request.id)
  const events = timelineForRequest(state, request.id)
  const decided = events.find((e) => e.event_type === 'spend_request.decided') ?? events[0]
  const auditLink = decided ? `/app/audit?event=${decided.id}` : '/app/audit'

  return (
    <>
      <PageHeader
        title={`${formatMoney(request.amount, request.currency)} to ${request.merchant}`}
        back={{ to: '/app/transactions', label: 'Transactions' }}
        description={
          <>
            Requested by {agent ? <Link to={`/app/agents/${agent.id}`}>{name}</Link> : name}{' '}
            <time dateTime={request.created_at} title={formatTimestamp(request.created_at)}>
              {timeAgo(request.created_at, now)}
            </time>
            .
          </>
        }
        actions={
          <Link to={auditLink} className="btn btn-secondary">
            See in audit log
          </Link>
        }
      />

      <div className="tx-statuses">
        <div className="tx-status">
          <span className="tx-status-label">Decision by AgentGate</span>
          <span>
            <DecisionStatus decision={request.decision} />
          </span>
          <span className="tx-status-note">{DECISION[request.decision].summary}</span>
        </div>
        <div className="tx-status">
          <span className="tx-status-label">Payment at PayPal</span>
          <span>
            <PaymentStatusBadge status={request.payment_status} />
          </span>
          <span className="tx-status-note" aria-live="polite">
            {explainPayment(request, approval)}
          </span>
        </div>
      </div>

      <div className="split">
        <div className="stack">
          <section className="card" aria-labelledby="tx-why">
            <div className="card-header">
              <h2 id="tx-why" className="card-title">
                {HEADINGS[request.decision]}
              </h2>
            </div>
            <div className="stack">
              <p>{explainDecision(request, name)}</p>
              <ReasonList reasons={request.reasons} />
              <div>
                <h3 className="tx-section-title">Rules matched</h3>
                {request.matched_rules.length ? (
                  <ul className="tx-codes">
                    {request.matched_rules.map((code) => (
                      <li key={code}>
                        <code>{code}</code>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="hint">None. Every rule passed.</p>
                )}
              </div>
            </div>
          </section>

          <section className="card" aria-labelledby="tx-details">
            <div className="card-header">
              <h2 id="tx-details" className="card-title">
                Request details
              </h2>
            </div>
            <dl className="kv">
              <dt>Agent</dt>
              <dd>{agent ? <Link to={`/app/agents/${agent.id}`}>{name}</Link> : name}</dd>
              <dt>Merchant</dt>
              <dd>{request.merchant}</dd>
              <dt>Amount</dt>
              <dd className="mono">
                {formatMoney(request.amount, request.currency)} {request.currency}
              </dd>
              <dt>Source</dt>
              <dd>{SOURCE[request.source].label}</dd>
              <dt>Purpose</dt>
              <dd className="tx-purpose">{request.purpose || '—'}</dd>
              <dt>Requested</dt>
              <dd>
                <time dateTime={request.created_at}>{formatTimestamp(request.created_at)}</time>
              </dd>
            </dl>
            <div className="field tx-field tx-field-gap">
              <span className="field-label">Request ID</span>
              <CopyField value={request.id} label="Request ID" />
            </div>
          </section>

          <section className="card" aria-labelledby="tx-payment">
            <div className="card-header">
              <h2 id="tx-payment" className="card-title">
                Payment
              </h2>
              <PaymentStatusBadge status={request.payment_status} />
            </div>
            {request.paypal_reference ? (
              <div className="field tx-field">
                <span className="field-label">PayPal reference</span>
                <CopyField value={request.paypal_reference} label="PayPal reference" />
              </div>
            ) : (
              <p className="hint">
                No PayPal reference.{' '}
                {request.payment_status === 'processing'
                  ? 'It appears once PayPal confirms the payment.'
                  : 'PayPal only gives one when a payment goes through.'}
              </p>
            )}
          </section>
        </div>

        <div className="stack">
          <section className="card" aria-labelledby="tx-approval">
            <div className="card-header">
              <h2 id="tx-approval" className="card-title">
                Human approval
              </h2>
              {approval && <ApprovalStatus outcome={approval.outcome} />}
            </div>
            {approval ? (
              <div className="stack">
                <dl className="kv">
                  <dt>Requested</dt>
                  <dd>{formatDateTime(approval.created_at)}</dd>
                  {approval.outcome === 'pending' ? (
                    <>
                      <dt>Expires</dt>
                      <dd>{timeAgo(approval.expires_at, now)}</dd>
                    </>
                  ) : (
                    <>
                      <dt>Decided by</dt>
                      <dd>{approval.approver ?? 'Nobody (expired)'}</dd>
                      {approval.decided_at && (
                        <>
                          <dt>Decided</dt>
                          <dd>{formatDateTime(approval.decided_at)}</dd>
                        </>
                      )}
                    </>
                  )}
                  {approval.note && (
                    <>
                      <dt>Note</dt>
                      <dd>“{approval.note}”</dd>
                    </>
                  )}
                </dl>
                <Link
                  to={`/app/approvals/${approval.id}`}
                  className={`btn btn-block ${approval.outcome === 'pending' ? 'btn-primary' : 'btn-secondary'}`}
                >
                  {approval.outcome === 'pending' ? 'Review this approval' : 'Open approval'}
                </Link>
              </div>
            ) : (
              <p className="hint">
                {request.decision === 'deny'
                  ? 'Denied requests are blocked outright and never go to a person.'
                  : 'This request did not need a person to approve it.'}
              </p>
            )}
          </section>

          <section className="card" aria-labelledby="tx-risk">
            <div className="card-header">
              <h2 id="tx-risk" className="card-title">
                Risk signals
              </h2>
            </div>
            <RiskList indicators={riskIndicators(state, request)} />
          </section>

          <section className="card" aria-labelledby="tx-timeline">
            <div className="card-header">
              <h2 id="tx-timeline" className="card-title">
                Timeline
              </h2>
              <Link to={auditLink} className="card-link">
                Audit log
              </Link>
            </div>
            <Timeline state={state} events={events} />
          </section>
        </div>
      </div>
    </>
  )
}
