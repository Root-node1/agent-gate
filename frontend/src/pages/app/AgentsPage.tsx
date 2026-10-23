import { useState } from 'react'
import { Link } from 'react-router'
import { Bot, KeyRound, Plus, Search } from 'lucide-react'
import { useDemoState } from '../../demo/store'
import { policyForAgent } from '../../demo/selectors'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import PageHeader from '../../ui/PageHeader'
import { AgentStatusBadge } from '../../ui/StatusBadges'
import { formatMoney, timeAgo } from '../../ui/format'
import { useNow, useSimulatedLoad } from '../../ui/hooks'
import { agentActivity } from './agents/agentStats'
import RegisterAgentModal from './agents/RegisterAgentModal'
import './AgentsPage.css'

function plural(n: number, word: string) {
  return `${n} ${n === 1 ? word : word + 's'}`
}

export default function AgentsPage() {
  const state = useDemoState()
  const loading = useSimulatedLoad()
  const now = useNow()
  const [query, setQuery] = useState('')
  const [registering, setRegistering] = useState(false)

  const q = query.trim().toLowerCase()
  const agents = state.agents.filter(
    (a) => !q || a.name.includes(q) || a.description.toLowerCase().includes(q),
  )
  const active = state.agents.filter((a) => a.status === 'active').length

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
              {active} active · {state.agents.length - active} suspended
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
              placeholder="Search by name or description"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>

        {loading ? (
          <SkeletonRows rows={4} />
        ) : state.agents.length === 0 ? (
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
                  {agents.map((agent) => {
                    const policy = policyForAgent(state, agent.id)
                    const activity = agentActivity(state, agent.id, now)
                    return (
                      <tr key={agent.id} className="row-link">
                        <td className="ag-name-cell">
                          <Link to={`/app/agents/${agent.id}`} className="row-anchor">
                            {agent.name}
                          </Link>
                          {agent.description && <p className="small muted ag-desc">{agent.description}</p>}
                        </td>
                        <td>
                          <AgentStatusBadge status={agent.status} />
                        </td>
                        <td>
                          {policy ? (
                            <Link to={`/app/policies/${policy.id}`} className="ag-cell-link">
                              {policy.name}
                            </Link>
                          ) : (
                            <span className="muted">None</span>
                          )}
                        </td>
                        <td className="ag-nowrap">
                          {agent.api_key_prefix ? (
                            <span className="mono">{agent.api_key_prefix}…</span>
                          ) : (
                            <span className="ag-nokey">
                              <KeyRound size={14} aria-hidden="true" /> Revoked
                            </span>
                          )}
                        </td>
                        <td className="ag-nowrap">
                          {activity.lastRequestAt ? (
                            <time dateTime={activity.lastRequestAt}>{timeAgo(activity.lastRequestAt, now)}</time>
                          ) : (
                            <span className="muted">Never</span>
                          )}
                        </td>
                        <td className="num ag-nowrap">
                          {formatMoney(activity.spendToday, activity.currency)}
                          <span className="ag-sub">{plural(activity.requestsToday, 'request')}</span>
                        </td>
                        <td className="num ag-nowrap">
                          {formatMoney(activity.spendMonth, activity.currency)}
                          <span className="ag-sub">{plural(activity.requestsMonth, 'request')}</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="table-footer">
              <span>
                Showing {agents.length} of {plural(state.agents.length, 'agent')}
              </span>
              <span>Spend counts allowed payments plus approvals that are waiting or approved.</span>
            </div>
          </>
        )}
      </section>

      <RegisterAgentModal open={registering} onClose={() => setRegistering(false)} />
    </div>
  )
}
