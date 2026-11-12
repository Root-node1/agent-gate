import { Link, useSearchParams } from 'react-router'
import { CircleCheckBig, Clock, Inbox } from 'lucide-react'
import { listApprovals, type Approval as ApiApproval, type ApprovalOutcome } from '../../api/approvals'
import { useApiResource } from '../../api/useApiResource'
import PageHeader from '../../ui/PageHeader'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import { ApprovalStatus } from '../../ui/StatusBadges'
import { formatDateTime, formatMoney, timeAgo } from '../../ui/format'
import { isTab, TABS } from './approvals/helpers'
import './ApprovalsPage.css'

const EMPTY: Record<ApprovalOutcome, { title: string; text: string }> = {
  pending: {
    title: 'All caught up',
    text: 'No payments are waiting for you. New ones appear here as soon as an agent needs a decision.',
  },
  approved: { title: 'No approved payments yet', text: 'Payments you approve show up here.' },
  denied: { title: 'No denied payments yet', text: 'Payments you deny show up here.' },
  expired: { title: 'Nothing has expired', text: 'Requests nobody decided in time show up here.' },
}

export default function ApprovalsPage() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('status')
  const tab: ApprovalOutcome = isTab(raw) ? raw : 'pending'

  const resource = useApiResource((signal) => listApprovals({ outcome: tab, signal }))

  if (resource.status === 'loading') {
    return (
      <div className="stack-lg">
        <PageHeader title="Approvals" description="Loading approvals…" />
        <div className="card">
          <SkeletonRows rows={4} />
        </div>
      </div>
    )
  }

  if (resource.status === 'error') {
    return (
      <div className="stack-lg">
        <PageHeader title="Approvals" description="Failed to load approvals" />
        <div className="card">
          <EmptyState
            icon={<Inbox size={24} />}
            title="Unable to load approvals"
            action={<button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>Retry</button>}
          >
            <span role="alert">{resource.error.message}</span>
          </EmptyState>
        </div>
      </div>
    )
  }

  const items = Array.isArray(resource.data)
    ? resource.data
    : 'results' in resource.data
      ? (resource.data as { results: ApiApproval[] }).results
      : []

  return (
    <div className="stack-lg">
      <PageHeader
        title="Approvals"
        description="Payments your agents cannot make until a person says yes. Check why each one was flagged, then approve or deny it."
      />

      <div className="tabs ap-tabs" role="group" aria-label="Filter by status">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className="tab"
            aria-pressed={tab === t.id}
            onClick={() => setParams(t.id === 'pending' ? {} : { status: t.id }, { replace: true })}
          >
            {t.label}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={tab === 'pending' ? <CircleCheckBig size={24} /> : <Inbox size={24} />}
            title={EMPTY[tab].title}
            action={
              tab === 'pending' ? (
                <Link to="/app/simulate" className="btn btn-secondary">
                  Simulate a request
                </Link>
              ) : undefined
            }
          >
            {EMPTY[tab].text}
          </EmptyState>
        </div>
      ) : (
        <>
          {tab === 'pending' && (
            <p className="muted small ap-list-note">
              {items.length} waiting · oldest first, so nothing sits too long
            </p>
          )}
          <ul className="ap-list" aria-label={`${TABS.find((t) => t.id === tab)?.label} approvals`}>
            {items.map((approval: ApiApproval) => (
              <ApprovalItem key={approval.id} approval={approval} tab={tab} />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function ApprovalItem({
  approval,
  tab,
}: {
  approval: ApiApproval
  tab: ApprovalOutcome
}) {
  return (
    <li className="card ap-item">
      <div className="ap-item-main">
        <div className="ap-item-title">
          <Link to={`/app/approvals/${approval.id}`} className="ap-item-link">
            <span className="ap-merchant">{approval.merchant}</span>
            <span className="visually-hidden">
              , {formatMoney(Number(approval.amount), approval.currency)} from {approval.agent_name}
            </span>
          </Link>
        </div>
        <p className="ap-item-meta">
          <span className="ap-agent">{approval.agent_name}</span>
          <span aria-hidden="true"> · </span>
          <span>
            Requested <time dateTime={approval.requested_at} title={formatDateTime(approval.requested_at)}>
              {timeAgo(approval.requested_at)}
            </time>
          </span>
        </p>
        {approval.reasons.length > 0 && (
          <ul className="ap-reasons" aria-label="Why it needs approval">
            {approval.reasons.map((r) => (
              <li key={r.code} className="ap-reason">
                {r.message}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="ap-item-side">
        <span className="ap-amount num">{formatMoney(Number(approval.amount), approval.currency)}</span>
        {tab === 'pending' ? (
          <span className="ap-expiry">
            <Clock size={14} aria-hidden="true" />
            Expires {formatDateTime(approval.expires_at)}
          </span>
        ) : (
          <span className="ap-outcome">
            <ApprovalStatus outcome={tab} />
            <span className="muted small">
              {approval.decided_at ? timeAgo(approval.decided_at) : timeAgo(approval.expires_at)}
            </span>
          </span>
        )}
      </div>
    </li>
  )
}
