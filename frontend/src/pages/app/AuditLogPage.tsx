import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Download, Lock, ScrollText, Search, SearchX } from 'lucide-react'
import { useDemoState } from '../../demo/store'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import PageHeader from '../../ui/PageHeader'
import { DecisionStatus } from '../../ui/StatusBadges'
import { formatTimestamp, shortId } from '../../ui/format'
import { useSimulatedLoad } from '../../ui/hooks'
import { EVENT, EVENT_GROUPS } from '../../ui/labels'
import { useToast } from '../../ui/toast-context'
import ActorLabel from './audit/ActorLabel'
import EventDrawer from './audit/EventDrawer'
import EventType from './audit/EventType'
import {
  ACTOR_FILTERS,
  PAGE_SIZE,
  applyFilters,
  buildRows,
  downloadCsv,
  formatClock,
  formatDay,
  hasFilters,
  readFilters,
  toCsv,
  type AuditFilters,
} from './audit/auditData'
import './AuditLogPage.css'

export default function AuditLogPage() {
  const state = useDemoState()
  const loading = useSimulatedLoad()
  const toast = useToast()
  const [params, setParams] = useSearchParams()

  const filters = readFilters(params)
  const rows = useMemo(() => buildRows(state), [state])
  const filtered = applyFilters(rows, filters)

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const page = Math.min(pageCount, Math.max(1, Number(params.get('page')) || 1))
  const start = (page - 1) * PAGE_SIZE
  const visible = filtered.slice(start, start + PAGE_SIZE)
  const eventId = params.get('event')

  function setFilter(key: keyof AuditFilters, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('page')
    setParams(next, { replace: true, preventScrollReset: true })
  }

  function clearFilters() {
    const next = new URLSearchParams()
    if (eventId) next.set('event', eventId)
    setParams(next, { replace: true, preventScrollReset: true })
  }

  function goToPage(n: number) {
    const next = new URLSearchParams(params)
    if (n > 1) next.set('page', String(n))
    else next.delete('page')
    setParams(next, { preventScrollReset: true })
  }

  function searchWith(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value === null) next.delete(key)
    else next.set(key, value)
    return `?${next.toString()}`
  }

  function closeDrawer() {
    const next = new URLSearchParams(params)
    next.delete('event')
    setParams(next, { replace: true, preventScrollReset: true })
  }

  function exportCsv() {
    const stamp = new Date().toISOString().slice(0, 10)
    downloadCsv(`agentgate-audit-${stamp}.csv`, toCsv(filtered))
    toast.show(`Exported ${filtered.length} ${filtered.length === 1 ? 'event' : 'events'} to CSV.`, 'success')
  }

  const filtering = hasFilters(filters)

  return (
    <div className="stack-lg">
      <PageHeader
        title="Audit log"
        description="Every request, decision, approval, payment and setting change, with who did it and why."
        actions={
          <button
            type="button"
            className="btn btn-secondary"
            onClick={exportCsv}
            disabled={loading || filtered.length === 0}
          >
            <Download size={16} aria-hidden="true" />
            Export CSV
          </button>
        }
      />

      <div className="notice tone-info au-trust">
        <Lock size={18} aria-hidden="true" />
        <p>
          <strong>Append-only.</strong> Events are written once and can't be edited or deleted by anyone, including
          admins. Export includes only the events that match your filters.
        </p>
      </div>

      <section className="card card-flush" aria-labelledby="au-results">
        <div className="au-filters" role="search" aria-label="Filter events">
          <div className="field au-filter-search">
            <label htmlFor="au-q">Search</label>
            <div className="search">
              <Search size={16} aria-hidden="true" />
              <input
                id="au-q"
                type="search"
                className="input"
                placeholder="Merchant, person, request ID, words…"
                value={filters.q}
                onChange={(e) => setFilter('q', e.target.value)}
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="au-type">Event type</label>
            <select id="au-type" value={filters.type} onChange={(e) => setFilter('type', e.target.value)}>
              <option value="">All events</option>
              {EVENT_GROUPS.map((group, i) => (
                <optgroup key={group.label} label={group.label}>
                  <option value={`group:${i}`}>All {group.label.toLowerCase()}</option>
                  {group.types.map((type) => (
                    <option key={type} value={type}>
                      {EVENT[type].label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="au-agent">Agent</label>
            <select id="au-agent" value={filters.agent} onChange={(e) => setFilter('agent', e.target.value)}>
              <option value="">All agents</option>
              {state.agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="au-actor">Done by</label>
            <select id="au-actor" value={filters.actor} onChange={(e) => setFilter('actor', e.target.value)}>
              <option value="">Anyone</option>
              {ACTOR_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="au-from">From</label>
            <input
              id="au-from"
              type="date"
              value={filters.from}
              max={filters.to || undefined}
              onChange={(e) => setFilter('from', e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="au-to">To</label>
            <input
              id="au-to"
              type="date"
              value={filters.to}
              min={filters.from || undefined}
              onChange={(e) => setFilter('to', e.target.value)}
            />
          </div>
        </div>

        <div className="au-results-bar">
          <p id="au-results" className="small" aria-live="polite">
            {loading
              ? 'Loading events…'
              : filtering
                ? `${filtered.length} of ${rows.length} events match`
                : `${rows.length} events, newest first`}
          </p>
          {filtering && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={clearFilters}>
              Clear filters
            </button>
          )}
        </div>

        {loading ? (
          <SkeletonRows rows={8} />
        ) : rows.length === 0 ? (
          <EmptyState icon={<ScrollText size={24} />} title="No events yet">
            Events appear here as soon as an agent sends a request or someone changes a setting.
          </EmptyState>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<SearchX size={24} />}
            title="No events match these filters"
            action={
              <button type="button" className="btn btn-secondary" onClick={clearFilters}>
                Clear filters
              </button>
            }
          >
            Try a wider date range or fewer filters.
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap">
              <table className="table au-table">
                <caption className="visually-hidden">
                  Audit events, newest first. Select a time to see full details.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Time</th>
                    <th scope="col">What happened</th>
                    <th scope="col">Done by</th>
                    <th scope="col">Agent</th>
                    <th scope="col">Decision</th>
                    <th scope="col">Request</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => (
                    <tr key={row.event.id} className="row-link">
                      <td className="au-time">
                        <Link
                          to={searchWith('event', String(row.event.id))}
                          className="row-anchor"
                          preventScrollReset
                        >
                          <time dateTime={row.event.created_at} title={formatTimestamp(row.event.created_at)}>
                            <span className="au-day">{formatDay(row.event.created_at)}</span>
                            <span className="au-clock">{formatClock(row.event.created_at)}</span>
                          </time>
                          <span className="visually-hidden">, view event details</span>
                        </Link>
                      </td>
                      <td className="au-what">
                        <EventType type={row.event.event_type} />
                        <span className="au-explanation">{row.explanation}</span>
                      </td>
                      <td>
                        <ActorLabel actor={row.event.actor} />
                      </td>
                      <td>{row.agent || <span className="muted">—</span>}</td>
                      <td>{row.decision ? <DecisionStatus decision={row.decision} /> : <span className="muted">—</span>}</td>
                      <td>
                        {row.event.spend_request_id ? (
                          <Link
                            to={`/app/transactions/${row.event.spend_request_id}`}
                            className="mono au-above-row"
                            aria-label={`Open transaction ${shortId(row.event.spend_request_id)}`}
                          >
                            {shortId(row.event.spend_request_id)}
                          </Link>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <nav className="table-footer" aria-label="Pages">
              <span>
                Showing {start + 1}–{start + visible.length} of {filtered.length}
              </span>
              <div className="cluster">
                <button type="button" className="btn btn-secondary" onClick={() => goToPage(page - 1)} disabled={page <= 1}>
                  Previous
                </button>
                <span aria-current="page">
                  Page {page} of {pageCount}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => goToPage(page + 1)}
                  disabled={page >= pageCount}
                >
                  Next
                </button>
              </div>
            </nav>
          </>
        )}
      </section>

      <EventDrawer state={state} eventId={eventId} onClose={closeDrawer} />
    </div>
  )
}
