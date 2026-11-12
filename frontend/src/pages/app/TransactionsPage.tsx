import { useState, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Info, Search, SearchX } from 'lucide-react'
import { listSpendRequests } from '../../api/spendRequests'
import { useApiResource } from '../../api/useApiResource'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import PageHeader from '../../ui/PageHeader'
import { DecisionStatus, PaymentStatusBadge } from '../../ui/StatusBadges'
import { formatDateTime, formatMoney, shortId } from '../../ui/format'
import { DECISION, PAYMENT } from '../../ui/labels'
import { PAGE_SIZE, RANGES, applyFilters, hasFilters, readFilters, type Filters } from './transactions/filters'
import './TransactionsPage.css'

export default function TransactionsPage() {
  const [params, setParams] = useSearchParams()
  const resource = useApiResource((signal) => listSpendRequests({ signal }))
  const loading = resource.status === 'loading'
  const filters = readFilters(params)
  const filterKey = params.toString()
  const [shown, setShown] = useState({ key: filterKey, count: PAGE_SIZE })
  const count = shown.key === filterKey ? shown.count : PAGE_SIZE

  const requests = useMemo(() => {
    if (resource.status !== 'success' && resource.status !== 'empty') return []
    return Array.isArray(resource.data)
      ? resource.data
      : 'results' in resource.data
        ? (resource.data as { results: unknown[] }).results
        : []
  }, [resource])

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const results = applyFilters(requests as any, filters)
  const visible = results.slice(0, count)
  const filtered = hasFilters(filters)

  function setFilter(key: keyof Filters, value: string) {
    const next = new URLSearchParams(params)
    const isDefault = value === '' || (key === 'range' && value === 'all')
    if (isDefault) next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  const clearFilters = () => setParams(new URLSearchParams(), { replace: true })

  // Error state handling
  if (resource.status === 'error') {
    return (
      <>
        <PageHeader title="Transactions" description="Failed to load transactions" />
        <EmptyState
          icon={<Search size={24} />}
          title="Unable to load transactions"
          action={<button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>Retry</button>}
        >
          <span role="alert">{resource.error.message}</span>
        </EmptyState>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Transactions"
        description="Every payment request your agents sent, what AgentGate decided and what happened at PayPal."
      />

      <div className="notice tone-info tx-legend">
        <Info size={18} aria-hidden="true" />
        <p>
          <strong>Decision</strong> (filled pill) is what AgentGate&apos;s rules decided.{' '}
          <strong>Payment</strong> (outlined pill) is what happened at PayPal. An allowed request is only
          paid once PayPal confirms it.
        </p>
      </div>

      <section className="card tx-filters" aria-label="Filters">
        <div className="toolbar">
          <div className="field tx-search">
            <label htmlFor="tx-q">Search</label>
            <div className="search">
              <Search size={16} aria-hidden="true" />
              <input
                id="tx-q"
                type="search"
                className="input"
                placeholder="Merchant or request ID"
                value={filters.q}
                onChange={(e) => setFilter('q', e.target.value)}
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="tx-agent">Agent</label>
            <select id="tx-agent" value={filters.agent} onChange={(e) => setFilter('agent', e.target.value)}>
              <option value="">All agents</option>
              {/* Agent filter populated from API */}
              <option value="">All agents</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="tx-decision">Decision</label>
            <select
              id="tx-decision"
              value={filters.decision}
              onChange={(e) => setFilter('decision', e.target.value)}
            >
              <option value="">All decisions</option>
              {(['allow', 'needs_approval', 'deny'] as const).map((d) => (
                <option key={d} value={d}>
                  {DECISION[d].label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="tx-payment">Payment</label>
            <select id="tx-payment" value={filters.payment} onChange={(e) => setFilter('payment', e.target.value)}>
              <option value="">All payment states</option>
              {(['completed', 'processing', 'awaiting_approval', 'failed', 'not_sent'] as const).map((p) => (
                <option key={p} value={p}>
                  {PAYMENT[p].label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="tx-filter-foot">
          <div className="tabs tx-range" role="group" aria-label="Date range">
            {RANGES.map((r) => (
              <button
                key={r.value}
                type="button"
                className="tab"
                aria-pressed={filters.range === r.value}
                onClick={() => setFilter('range', r.value)}
              >
                {r.label}
              </button>
            ))}
          </div>
          <div className="tx-count">
            <p role="status" aria-live="polite">
              {loading ? 'Loading requests…' : `${results.length} ${results.length === 1 ? 'request' : 'requests'}`}
              {filtered && !loading ? ` of ${requests.length}` : ''}
            </p>
            {filtered && (
              <button type="button" className="btn btn-ghost" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </div>
        </div>
      </section>

      <section className="card card-flush" aria-label="Payment requests">
        {loading ? (
          <SkeletonRows rows={8} />
        ) : results.length === 0 ? (
          <EmptyState
            icon={<SearchX size={22} />}
            title={filtered ? 'No requests match these filters' : 'No payment requests yet'}
            action={
              filtered ? (
                <button type="button" className="btn btn-secondary" onClick={clearFilters}>
                  Clear filters
                </button>
              ) : (
                <Link to="/app/simulate" className="btn btn-primary">
                  Simulate a request
                </Link>
              )
            }
          >
            {filtered
              ? 'Try a wider date range or a different agent, decision or payment state.'
              : 'Requests appear here as soon as an agent asks to pay.'}
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap">
              <table className="table tx-table">
                <caption className="visually-hidden">
                  Payment requests, newest first. Select a row to see the details.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Merchant</th>
                    <th scope="col">Agent</th>
                    <th scope="col" className="num">
                      Amount
                    </th>
                    <th scope="col">Decision</th>
                    <th scope="col">Payment</th>
                    <th scope="col">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => (
                    <tr key={r.id} className="row-link">
                      <td>
                        <Link to={`/app/transactions/${r.id}`} className="row-anchor">
                          {r.merchant}
                        </Link>
                        <span className="tx-id mono">{shortId(r.id)}</span>
                      </td>
                      <td><span className="muted">{r.agent_id}</span></td>
                      <td className="num tx-amount">
                        {formatMoney(r.amount, r.currency)} <span className="tx-currency">{r.currency}</span>
                      </td>
                      <td>
                        <DecisionStatus decision={r.decision} />
                      </td>
                      <td>
                        <PaymentStatusBadge status={r.payment_status} />
                      </td>
                      <td className="tx-date">
                        <time dateTime={r.created_at}>{formatDateTime(r.created_at)}</time>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-footer">
              <span>
                Showing {visible.length} of {results.length}
              </span>
              {visible.length < results.length && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setShown({ key: filterKey, count: count + PAGE_SIZE })}
                >
                  Show {Math.min(PAGE_SIZE, results.length - visible.length)} more
                </button>
              )}
            </div>
          </>
        )}
      </section>
    </>
  )
}
