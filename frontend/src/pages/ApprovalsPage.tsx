import { useEffect, useState } from 'react'
import { USING_MOCK_DATA, listApprovals, type Approval } from '../api/approvals'
import ApprovalCard from '../components/ApprovalCard'

type Tab = 'pending' | 'decided'

interface Loaded {
  /** Which load this result belongs to, so a retry shows the loading state. */
  attempt: number
  approvals?: Approval[]
  error?: string
}

export default function ApprovalsPage() {
  const [tab, setTab] = useState<Tab>('pending')
  const [attempt, setAttempt] = useState(0)
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [announcement, setAnnouncement] = useState('')

  useEffect(() => {
    let cancelled = false
    listApprovals().then(
      (approvals) => !cancelled && setLoaded({ attempt, approvals }),
      () => !cancelled && setLoaded({ attempt, error: 'Could not load approvals.' }),
    )
    return () => {
      cancelled = true
    }
  }, [attempt])

  function handleDecided(updated: Approval) {
    setLoaded((prev) =>
      prev?.approvals
        ? { ...prev, approvals: prev.approvals.map((a) => (a.id === updated.id ? updated : a)) }
        : prev,
    )
    const { amount, currency, merchant } = updated.spend_request
    setAnnouncement(
      `${updated.outcome === 'approved' ? 'Approved' : 'Denied'} ${amount} ${currency} to ${merchant}.`,
    )
  }

  const current = loaded?.attempt === attempt ? loaded : null
  const approvals = current?.approvals ?? []
  const pending = approvals
    .filter((a) => a.outcome === 'pending')
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
  const decided = approvals
    .filter((a) => a.outcome !== 'pending')
    .sort((a, b) => (b.decided_at ?? '').localeCompare(a.decided_at ?? ''))
  const shown = tab === 'pending' ? pending : decided

  let body
  if (!current) {
    body = <p className="panel empty">Loading approvals…</p>
  } else if (current.error) {
    body = (
      <div className="form-error" role="alert">
        <p>{current.error}</p>
        <button type="button" className="button button-secondary retry" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    )
  } else if (shown.length === 0) {
    body = (
      <p className="panel empty">
        {tab === 'pending' ? 'All caught up. No payments are waiting for you.' : 'Nothing decided yet.'}
      </p>
    )
  } else {
    body = (
      <div className="approval-list">
        {shown.map((approval) => (
          <ApprovalCard key={approval.id} approval={approval} onDecided={handleDecided} />
        ))}
      </div>
    )
  }

  return (
    <>
      <div className="page-intro">
        <h2>Approvals</h2>
        <p>Payments that need a person to say yes or no. Oldest first.</p>
      </div>

      {USING_MOCK_DATA && (
        <p className="notice" role="note">
          <strong>Sample data.</strong> The approvals API is not built yet, so nothing here moves real
          money. Decisions reset when you reload.
        </p>
      )}

      <div className="tabs" role="group" aria-label="Filter approvals">
        <button
          type="button"
          className="tab"
          aria-pressed={tab === 'pending'}
          onClick={() => setTab('pending')}
        >
          Waiting{current?.approvals && ` (${pending.length})`}
        </button>
        <button
          type="button"
          className="tab"
          aria-pressed={tab === 'decided'}
          onClick={() => setTab('decided')}
        >
          Decided{current?.approvals && ` (${decided.length})`}
        </button>
      </div>

      <p className="visually-hidden" aria-live="polite">
        {announcement}
      </p>

      {body}
    </>
  )
}
