import { useState, useMemo } from 'react'
import { Link } from 'react-router'
import { Bot, KeyRound, Plus, Search } from 'lucide-react'
import { listAgents, type AgentListItem } from '../../api/agents'
import { useApiResource } from '../../api/useApiResource'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import PageHeader from '../../ui/PageHeader'
import { AgentStatusBadge } from '../../ui/StatusBadges'
import RegisterAgentModal from './agents/RegisterAgentModal'
import './AgentsPage.css'

function plural(n: number, word: string) {
  return `${n} ${n === 1 ? word : word + 's'}`
}

export default function AgentsPage() {
  const [query, setQuery] = useState('')
  const [registering, setRegistering] = useState(false)

  const resource = useApiResource((signal) => listAgents({ signal }))

  const q = query.trim().toLowerCase()
  const agents = useMemo(() => {
    if (resource.status !== 'success' && resource.status !== 'empty') return []
    const items = Array.isArray(resource.data)
      ? resource.data
      : 'results' in resource.data
        ? (resource.data as { results: AgentListItem[] }).results
        : []
    return items.filter(
      (a: AgentListItem) => !q || a.name.toLowerCase().includes(q),
    )
  }, [resource, q])

  const totalCount = useMemo(() => {
    if (resource.status !== 'success' && resource.status !== 'empty') return 0
    return 'count' in resource.data ? (resource.data as { count: number }).count : agents.length
  }, [resource, agents.length])

  const active = useMemo(() => {
    if (resource.status !== 'success' && resource.status !== 'empty') return 0
    const items = Array.isArray(resource.data)
      ? resource.data
      : 'results' in resource.data
        ? (resource.data as { results: AgentListItem[] }).results
        : []
    return items.filter((a: AgentListItem) => a.status === 'active').length
  }, [resource])

  if (resource.status === 'loading') {
    return (
      <div className="stack-lg">
        <PageHeader title="Agents" description="Loading agents…" />
        <section className="card card-flush">
          <SkeletonRows rows={4} />
        </section>
      </div>
    )
  }

  if (resource.status === 'error') {
    return (
      <div className="stack-lg">
        <PageHeader title="Agents" description="Failed to load agents" />
        <EmptyState
          icon={<Bot size={24} />}
          title="Unable to load agents"
          action={<button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>Retry</button>}
        >
          <span role="alert">{resource.error.message}</span>
        </EmptyState>
      </div>
    )
  }

  const allItems = Array.isArray(resource.data)
    ? resource.data
    : 'results' in resource.data
      ? (resource.data as { results: AgentListItem[] }).results
      : []

  return (
    <div className="stack-lg">
      <PageHeader
        title="Agents"
        description="Every AI agent that can ask AgentGate to pay. Each has its own API key and spending policy."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setRegistering(true)}>
            <Plus size={18} aria-hidden="true" />
            Register agent
          </button>
        }
      />

      <section className="card card-flush" aria-labelledby="ag-list-title">
        <div className="card-header">
          <div>
            <h2 id="ag-list-title" className="card-title">
              Connected agents
            </h2>
            <p className="card-subtitle">
              {active} active · {totalCount - active} suspended
            </p>
          </div>
          <div className="search ag-search">
            <Search size={18} aria-hidden="true" />
            <label htmlFor="ag-search" className="visually-hidden">
              Search agents
            </label>
            <input
              id="ag-search"
              type="search"
              className="input"
              placeholder="Search by name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>

        {allItems.length === 0 ? (
          <EmptyState
            icon={<Bot size={24} />}
            title="No agents yet"
            action={
              <button type="button" className="btn btn-primary" onClick={() => setRegistering(true)}>
                Register your first agent
              </button>
            }
          >
            Register an agent to get an API key it can use to request payments.
          </EmptyState>
        ) : agents.length === 0 ? (
          <EmptyState
            icon={<Search size={24} />}
            title="No agents match your search"
            action={
              <button type="button" className="btn btn-secondary" onClick={() => setQuery('')}>
                Clear search
              </button>
            }
          >
            Nothing matches “{query.trim()}”.
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap">
              <table className="table ag-table">
                <thead>
                  <tr>
                    <th scope="col">Agent</th>
                    <th scope="col">Status</th>
                    <th scope="col">Policy</th>
                    <th scope="col">API key</th>
                    <th scope="col">Last request</th>
                    <th scope="col" className="num">
                      Today
                    </th>
                    <th scope="col" className="num">
                      This month
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((agent: AgentListItem) => (
                    <tr key={agent.id} className="row-link">
                      <td className="ag-name-cell">
                        <Link to={`/app/agents/${agent.id}`} className="row-anchor">
                          {agent.name}
                        </Link>
                      </td>
                      <td>
                        <AgentStatusBadge status={agent.status} />
                      </td>
                      <td>
                        <span className="muted">—</span>
                      </td>
                      <td className="ag-nowrap">
                        {agent.current_key_prefix ? (
                          <span className="mono">{agent.current_key_prefix}…</span>
                        ) : (
                          <span className="ag-nokey">
                            <KeyRound size={14} aria-hidden="true" /> Revoked
                          </span>
                        )}
                      </td>
                      <td className="ag-nowrap">
                        <span className="muted">—</span>
                      </td>
                      <td className="num ag-nowrap">
                        <span className="muted">—</span>
                      </td>
                      <td className="num ag-nowrap">
                        <span className="muted">—</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-footer">
              <span>
                Showing {agents.length} of {plural(totalCount, 'agent')}
              </span>
            </div>
          </>
        )}
      </section>

      <RegisterAgentModal open={registering} onClose={() => setRegistering(false)} />
    </div>
  )
}
