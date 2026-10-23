import { Link, useSearchParams } from 'react-router'
import { AlertTriangle, CircleCheckBig, Clock, Inbox } from 'lucide-react'
import { useDemoState } from '../../demo/store'
import { agentName, requestById, riskIndicators } from '../../demo/selectors'
import type { Approval, ApprovalOutcome, DemoState } from '../../demo/types'
import PageHeader from '../../ui/PageHeader'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import { ApprovalStatus } from '../../ui/StatusBadges'
import { formatDateTime, formatMoney, timeAgo } from '../../ui/format'
import { useNow, useSimulatedLoad } from '../../ui/hooks'
import { effectiveOutcome, escalationLabels, expiresIn, highRisk, isTab, personName, TABS } from './approvals/helpers'
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
  const state = useDemoState()
  const now = useNow(15_000)
  const loading = useSimulatedLoad()
  const [params, setParams] = useSearchParams()
  const raw = params.get('status')
  const tab: ApprovalOutcome = isTab(raw) ? raw : 'pending'

  const groups: Record<ApprovalOutcome, Approval[]> = { pending: [], approved: [], denied: [], expired: [] }
  for (const approval of state.approvals) groups[effectiveOutcome(approval, now)].push(approval)
  // The queue is worked oldest first; decided items show the latest decision first.
  groups.pending.sort((a, b) => a.created_at.localeCompare(b.created_at))
  for (const key of ['approved', 'denied', 'expired'] as const) {
    groups[key].sort((a, b) => (b.decided_at ?? b.expires_at).localeCompare(a.decided_at ?? a.expires_at))
  }
  const items = groups[tab]

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
            <span className="ap-tab-count">{groups[t.id].length}</span>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="card">
          <SkeletonRows rows={4} />
        </div>
      ) : items.length === 0 ? (
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
            {items.map((approval) => (
              <ApprovalItem key={approval.id} state={state} approval={approval} tab={tab} now={now} />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function ApprovalItem({
  state,
  approval,
  tab,
  now,
}: {
  state: DemoState
  approval: Approval
  tab: ApprovalOutcome
  now: number
}) {
  const request = requestById(state, approval.spend_request_id)
  if (!request) return null
  const reasons = escalationLabels(request)
  const risky = highRisk(riskIndicators(state, request))
  const expiry = expiresIn(approval.expires_at, now)
  const agent = agentName(state, request.agent_id)

  return (
    <li className={`card ap-item ${risky && tab === 'pending' ? 'ap-item-risky' : ''}`}>
      <div className="ap-item-main">
        <div className="ap-item-title">
          <Link to={`/app/approvals/${approval.id}`} className="ap-item-link">
            <span className="ap-merchant">{request.merchant}</span>
            <span className="visually-hidden">
              , {formatMoney(request.amount, request.currency)} from {agent}
            </span>
          </Link>
          {risky && (
            <span className="pill pill-solid tone-deny">
              <AlertTriangle size={14} aria-hidden="true" />
              High risk
            </span>
          )}
        </div>
        <p className="ap-item-meta">
          <span className="ap-agent">{agent}</span>
          <span aria-hidden="true"> · </span>
          <span>
            Requested <time dateTime={request.created_at} title={formatDateTime(request.created_at)}>
              {timeAgo(request.created_at, now)}
            </time>
          </span>
        </p>
        {reasons.length > 0 && (
          <ul className="ap-reasons" aria-label="Why it needs approval">
            {reasons.map((label) => (
              <li key={label} className="ap-reason">
                {label}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="ap-item-side">
        <span className="ap-amount num">{formatMoney(request.amount, request.currency)}</span>
        {tab === 'pending' ? (
          <span className={`ap-expiry ${expiry.urgent ? 'ap-expiry-urgent' : ''}`}>
            <Clock size={14} aria-hidden="true" />
            {expiry.text}
          </span>
        ) : (
          <span className="ap-outcome">
            <ApprovalStatus outcome={tab} />
            <span className="muted small">
              {tab === 'expired'
                ? `${timeAgo(approval.expires_at, now)}`
                : `${personName(state, approval.approver)} · ${timeAgo(approval.decided_at ?? approval.created_at, now)}`}
            </span>
          </span>
        )}
      </div>
    </li>
  )
}
