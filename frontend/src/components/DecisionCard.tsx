import type { ReactNode } from 'react'
import type { SpendRequest } from '../api/spendRequests'
import DecisionBadge from './DecisionBadge'
import { APPROVAL_LABELS, DECISION_LABELS, SOURCE_LABELS, formatTime } from './labels'

interface Props {
  request: SpendRequest
  actions?: ReactNode
}

export default function DecisionCard({ request, actions }: Props) {
  return (
    <section
      className={`panel decision decision-${request.decision}`}
      aria-live="polite"
      aria-label="Decision"
    >
      <DecisionBadge decision={request.decision} />

      <div className="decision-summary">
        <p className="amount">
          {request.amount} {request.currency}
        </p>
        <p>to {request.merchant}</p>
        <p className="hint">{DECISION_LABELS[request.decision].summary}</p>
      </div>

      {request.reasons.length > 0 && (
        <>
          <h3>Why</h3>
          <ul className="reasons">
            {request.reasons.map((reason) => (
              <li key={reason.code}>
                {reason.message}
                <code>{reason.code}</code>
              </li>
            ))}
          </ul>
        </>
      )}

      <dl className="details">
        <dt>Source</dt>
        <dd>{SOURCE_LABELS[request.source]}</dd>
        {request.purpose && (
          <>
            <dt>Purpose</dt>
            <dd>{request.purpose}</dd>
          </>
        )}
        {request.approval && (
          <>
            <dt>Approval</dt>
            <dd>{APPROVAL_LABELS[request.approval]}</dd>
          </>
        )}
        <dt>Request ID</dt>
        <dd>
          <code>{request.id}</code>
        </dd>
        <dt>Time</dt>
        <dd>{formatTime(request.created_at)}</dd>
      </dl>

      {actions && <div className="card-actions">{actions}</div>}
    </section>
  )
}
