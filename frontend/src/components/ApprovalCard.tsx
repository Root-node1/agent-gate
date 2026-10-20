import { useState } from 'react'
import { approve, deny, type Approval } from '../api/approvals'
import { ApiError } from '../api/spendRequests'
import { SOURCE_LABELS, formatTime, timeAgo } from './labels'

type Action = 'approve' | 'deny'

const ACTION_COPY: Record<Action, { confirm: string; busy: string; notePlaceholder: string }> = {
  approve: {
    confirm: 'Yes, approve payment',
    busy: 'Approving…',
    notePlaceholder: 'Optional: why is this OK?',
  },
  deny: {
    confirm: 'Yes, deny payment',
    busy: 'Denying…',
    notePlaceholder: 'Optional: why are you denying it?',
  },
}

interface Props {
  approval: Approval
  onDecided: (approval: Approval) => void
}

export default function ApprovalCard({ approval, onDecided }: Props) {
  const request = approval.spend_request
  const [action, setAction] = useState<Action | null>(null)
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const headingId = `approval-${approval.id}-title`
  const isPending = approval.outcome === 'pending'
  const untrusted = request.source === 'untrusted'

  async function confirm() {
    if (!action) return
    setSubmitting(true)
    setError('')
    try {
      onDecided(await (action === 'approve' ? approve : deny)(approval.id, note))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save. Try again.')
      setSubmitting(false)
    }
  }

  function cancel() {
    setAction(null)
    setNote('')
    setError('')
  }

  return (
    <article className={`panel approval approval-${approval.outcome}`} aria-labelledby={headingId}>
      <div className="approval-head">
        <h3 id={headingId} className="amount">
          {request.amount} {request.currency}
          <span className="approval-merchant"> to {request.merchant}</span>
        </h3>
        <span className="hint" title={formatTime(approval.created_at)}>
          {timeAgo(approval.created_at)}
        </span>
      </div>

      <p className="approval-meta">
        Agent <strong>{approval.agent}</strong>
        <span aria-hidden="true"> · </span>
        <span className={untrusted ? 'source-warning' : undefined}>
          {untrusted && <span aria-hidden="true">⚠ </span>}
          {SOURCE_LABELS[request.source]}
        </span>
      </p>

      {request.purpose && <p className="approval-purpose">“{request.purpose}”</p>}

      <h4 className="approval-why">Needs a person because</h4>
      <ul className="reasons">
        {request.reasons.map((reason) => (
          <li key={reason.code}>
            {reason.message}
            <code>{reason.code}</code>
          </li>
        ))}
      </ul>

      {!isPending && (
        <p className={`outcome outcome-${approval.outcome}`}>
          <span aria-hidden="true">{approval.outcome === 'approved' ? '✓ ' : '✕ '}</span>
          {approval.outcome === 'approved' ? 'Approved' : 'Denied'} by {approval.approver}
          {approval.decided_at && ` ${timeAgo(approval.decided_at)}`}
          {approval.note && <span className="outcome-note">Note: {approval.note}</span>}
        </p>
      )}

      {isPending && !action && (
        <div className="approval-actions">
          <button type="button" className="button button-approve" onClick={() => setAction('approve')}>
            Approve
          </button>
          <button type="button" className="button button-deny" onClick={() => setAction('deny')}>
            Deny
          </button>
        </div>
      )}

      {isPending && action && (
        <div className={`confirm confirm-${action}`} role="group" aria-label="Confirm decision">
          <p className="confirm-title">
            {action === 'approve'
              ? `Approve ${request.amount} ${request.currency} to ${request.merchant}?`
              : `Deny ${request.amount} ${request.currency} to ${request.merchant}?`}
          </p>
          <div className="field">
            <label htmlFor={`note-${approval.id}`}>Note</label>
            <input
              id={`note-${approval.id}`}
              placeholder={ACTION_COPY[action].notePlaceholder}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={255}
              autoFocus
            />
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="approval-actions">
            <button
              type="button"
              className={`button ${action === 'approve' ? 'button-approve' : 'button-deny-solid'}`}
              onClick={confirm}
              disabled={submitting}
            >
              {submitting ? ACTION_COPY[action].busy : ACTION_COPY[action].confirm}
            </button>
            <button
              type="button"
              className="button button-secondary"
              onClick={cancel}
              disabled={submitting}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </article>
  )
}
