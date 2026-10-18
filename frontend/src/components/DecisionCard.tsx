import type { Decision, SpendRequest } from '../api/spendRequests'

const DECISION_LABELS: Record<Decision, { icon: string; label: string; summary: string }> = {
  allow: { icon: '✓', label: 'Allowed', summary: 'This payment can go ahead.' },
  deny: { icon: '✕', label: 'Denied', summary: 'This payment was blocked.' },
  needs_approval: {
    icon: '!',
    label: 'Needs approval',
    summary: 'A person must approve this before it is paid.',
  },
  pending: { icon: '…', label: 'Pending', summary: 'No decision yet.' },
}

const SOURCE_LABELS = {
  trusted: 'Trusted (operator or user)',
  untrusted: 'Untrusted (web page, email or invoice)',
  unknown: 'Unknown',
}

export default function DecisionCard({ request }: { request: SpendRequest }) {
  const { icon, label, summary } = DECISION_LABELS[request.decision]

  return (
    <section
      className={`panel decision decision-${request.decision}`}
      aria-live="polite"
      aria-label="Decision"
    >
      <span className={`badge badge-${request.decision}`}>
        <span aria-hidden="true">{icon}</span>
        {label}
      </span>

      <div className="decision-summary">
        <p className="amount">
          {request.amount} {request.currency}
        </p>
        <p>to {request.merchant}</p>
        <p className="hint">{summary}</p>
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
            <dd>{request.approval}</dd>
          </>
        )}
        <dt>Request ID</dt>
        <dd>
          <code>{request.id}</code>
        </dd>
        <dt>Time</dt>
        <dd>{new Date(request.created_at).toLocaleString()}</dd>
      </dl>
    </section>
  )
}
