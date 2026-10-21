import { useState } from 'react'
import { Link } from 'react-router'
import { Activity, CircleCheck, CircleX, Clock, FlaskConical, Inbox } from 'lucide-react'
import { getDemoState, useDemoState } from '../../demo/store'
import { decisionsByDay, decisionTotals, pendingApprovals } from '../../demo/selectors'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import PageHeader from '../../ui/PageHeader'
import StatCard from '../../ui/StatCard'
import { percent } from '../../ui/format'
import { useNow, useSimulatedLoad } from '../../ui/hooks'
import ActivityFeed from './overview/ActivityFeed'
import ApprovalsCallout from './overview/ApprovalsCallout'
import BudgetCard from './overview/BudgetCard'
import DecisionsChart from './overview/DecisionsChart'
import RecentRequests from './overview/RecentRequests'
import { duration, feedEvents, WINDOW_DAYS, windowStart } from './overview/helpers'
import './OverviewPage.css'

const statSkeleton = <span className="skeleton ov-stat-skeleton" aria-label="Loading" />

export default function OverviewPage() {
  const state = useDemoState()
  const loading = useSimulatedLoad()
  const now = useNow(15_000)
  // Events after this id arrived while the page was open; the feed animates them in.
  const [baselineEventId] = useState(() => getDemoState().events[0]?.id ?? 0)

  const since = windowStart(now).toISOString()
  const inWindow = state.requests.filter((r) => r.created_at >= since)
  const totals = decisionTotals(inWindow)
  const pending = pendingApprovals(state)
  const days = decisionsByDay(state, WINDOW_DAYS, new Date(now))
  const recent = state.requests.slice(0, 6)
  const feed = feedEvents(state.events, 6)
  const share = (n: number) => `${percent(n, totals.total)}% of requests`

  return (
    <div className="stack-lg">
      <PageHeader
        title="Overview"
        description={`What your AI agents are doing and whether spending is under control. Figures cover the last ${WINDOW_DAYS} days.`}
        actions={
          <Link to="/app/simulate" className="btn btn-secondary">
            <FlaskConical size={16} aria-hidden="true" />
            Simulate a request
          </Link>
        }
      />

      {loading ? (
        <div className="skeleton ov-callout-skeleton" aria-hidden="true" />
      ) : (
        <ApprovalsCallout state={state} pending={pending} now={now} />
      )}

      <section aria-label={`Summary, last ${WINDOW_DAYS} days`} className="grid grid-4 ov-stats">
        <StatCard
          label="Total requests"
          value={loading ? statSkeleton : totals.total.toLocaleString()}
          detail={`Last ${WINDOW_DAYS} days`}
          icon={<Activity size={18} />}
          tone="info"
        />
        <StatCard
          label="Allowed"
          value={loading ? statSkeleton : totals.allow.toLocaleString()}
          detail={loading ? ' ' : share(totals.allow)}
          icon={<CircleCheck size={18} />}
          tone="allow"
        />
        <StatCard
          label="Denied"
          value={loading ? statSkeleton : totals.deny.toLocaleString()}
          detail={loading ? ' ' : share(totals.deny)}
          icon={<CircleX size={18} />}
          tone="deny"
        />
        <StatCard
          label="Pending approvals"
          value={loading ? statSkeleton : pending.length.toLocaleString()}
          detail={
            loading
              ? ' '
              : pending.length
                ? `Oldest waiting ${duration(pending[0].created_at, now)}`
                : 'Nothing waiting right now'
          }
          icon={<Clock size={18} />}
          tone="approval"
          to="/app/approvals"
        />
      </section>

      <div className="split ov-columns">
        <div className="ov-column">
          <section className="card" aria-labelledby="ov-chart-title">
            <div className="card-header">
              <div>
                <h2 className="card-title" id="ov-chart-title">
                  Decisions over time
                </h2>
                <p className="card-subtitle">Requests per day by outcome, last {WINDOW_DAYS} days</p>
              </div>
              <Link to="/app/transactions" className="card-link">
                Transactions
              </Link>
            </div>
            {loading ? <div className="skeleton ov-chart-skeleton" aria-hidden="true" /> : <DecisionsChart days={days} />}
          </section>
          <section className="card card-flush" aria-labelledby="ov-recent-title">
            <div className="card-header">
              <div>
                <h2 className="card-title" id="ov-recent-title">
                  Recent decisions
                </h2>
                <p className="card-subtitle">The latest spend requests from your agents</p>
              </div>
              <Link to="/app/transactions" className="card-link">
                View all
              </Link>
            </div>
            {loading ? (
              <SkeletonRows rows={6} />
            ) : recent.length === 0 ? (
              <EmptyState
                icon={<Inbox size={22} />}
                title="No spend requests yet"
                action={
                  <Link to="/app/simulate" className="btn btn-primary">
                    Simulate a request
                  </Link>
                }
              >
                When an agent asks to pay, the decision shows up here.
              </EmptyState>
            ) : (
              <RecentRequests state={state} requests={recent} now={now} />
            )}
          </section>
        </div>
        <div className="ov-column">
          {loading ? (
            <section className="card" aria-label="Budget">
              <SkeletonRows rows={6} />
            </section>
          ) : (
            <BudgetCard state={state} now={now} />
          )}
          <section className="card card-flush" aria-labelledby="ov-feed-title">
            <div className="card-header">
              <div className="cluster">
                <h2 className="card-title" id="ov-feed-title">
                  Live activity
                </h2>
                <span className="ov-live">
                  <span className="ov-live-dot" aria-hidden="true" />
                  Live
                </span>
              </div>
              <Link to="/app/audit" className="card-link">
                Audit log
              </Link>
            </div>
            {loading ? (
              <SkeletonRows rows={6} />
            ) : feed.length === 0 ? (
              <EmptyState icon={<Activity size={22} />} title="No activity yet">
                Decisions, approvals and payments appear here as they happen.
              </EmptyState>
            ) : (
              <div aria-live="polite" aria-relevant="additions">
                <ActivityFeed state={state} events={feed} now={now} newerThan={baselineEventId} />
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
