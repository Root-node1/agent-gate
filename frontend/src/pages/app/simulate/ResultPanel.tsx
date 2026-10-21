import type { Ref } from 'react'
import { Link } from 'react-router'
import { CircleAlert, FlaskConical, Loader2 } from 'lucide-react'
import { agentName, approvalForRequest, requestById, timelineForRequest } from '../../../demo/selectors'
import type { DemoState } from '../../../demo/types'
import ReasonList from '../../../ui/ReasonList'
import { DecisionStatus, PaymentStatusBadge } from '../../../ui/StatusBadges'
import { formatMoney } from '../../../ui/format'
import { explainDecision, explainPayment } from '../transactions/explain'
import { RULE_COUNT } from './scenarios'

interface Props {
  state: DemoState
  checking: boolean
  requestId: string | null
  error: string | null
  /** What was sent, e.g. a scenario title. */
  label: string
  headingRef: Ref<HTMLHeadingElement>
}

export default function ResultPanel({ state, checking, requestId, error, label, headingRef }: Props) {
  const request = requestById(state, requestId)
  const approval = request ? approvalForRequest(state, request.id) : undefined
  const decided = request
    ? timelineForRequest(state, request.id).find((e) => e.event_type === 'spend_request.decided')
    : undefined

  return (
    <section className={`card sim-result ${request ? `sim-result-${request.decision}` : ''}`} aria-labelledby="sim-result">
      <div className="card-header">
        <h2 id="sim-result" className="card-title" ref={headingRef} tabIndex={-1}>
          Result{label && (checking || request || error) ? `: ${label}` : ''}
        </h2>
      </div>

      <div aria-live="polite">
        {checking ? (
          <div className="sim-checking">
            <Loader2 size={20} className="sim-spin" aria-hidden="true" />
            <div className="sim-checking-body">
              <p>Checking {RULE_COUNT} rules…</p>
              <div className="sim-progress" aria-hidden="true">
                <div className="sim-progress-fill" />
              </div>
            </div>
          </div>
        ) : error ? (
          <div className="notice tone-deny sim-error" role="alert">
            <CircleAlert size={18} aria-hidden="true" />
            <div>
              <p>
                <strong>Request rejected before any rule ran.</strong>
              </p>
              <p>{error}</p>
            </div>
          </div>
        ) : request ? (
          <div className="stack sim-result-body">
            <p className="sim-summary">
              {agentName(state, request.agent_id)} asked to pay{' '}
              <strong>{formatMoney(request.amount, request.currency)}</strong> to <strong>{request.merchant}</strong>.
            </p>
            <div className="sim-statuses">
              <div className="sim-status">
                <span className="sim-status-label">AgentGate decided</span>
                <DecisionStatus decision={request.decision} />
              </div>
              <div className="sim-status">
                <span className="sim-status-label">PayPal payment</span>
                <PaymentStatusBadge status={request.payment_status} />
              </div>
            </div>
            <p>{explainDecision(request, agentName(state, request.agent_id))}</p>
            <ReasonList reasons={request.reasons} />
            <p className="hint">{explainPayment(request, approval)}</p>

            <div className="sim-next">
              {approval && approval.outcome === 'pending' && (
                <Link to={`/app/approvals/${approval.id}`} className="btn btn-primary">
                  Review in approval queue
                </Link>
              )}
              <Link to={`/app/transactions/${request.id}`} className="btn btn-secondary">
                View transaction
              </Link>
              <Link to={decided ? `/app/audit?event=${decided.id}` : '/app/audit'} className="btn btn-ghost">
                See it in the audit log
              </Link>
            </div>
          </div>
        ) : (
          <div className="sim-empty">
            <FlaskConical size={20} aria-hidden="true" />
            <p>Run a scenario or send your own request. The decision shows up here.</p>
          </div>
        )}
      </div>
    </section>
  )
}
