import { Link } from 'react-router'
import { Info } from 'lucide-react'
import type { DemoState } from '../../../demo/types'
import Badge from '../../../ui/Badge'
import EmptyState, { SkeletonRows } from '../../../ui/EmptyState'
import { AgentStatusBadge } from '../../../ui/StatusBadges'
import { formatTimestamp, timeAgo } from '../../../ui/format'
import { useNow } from '../../../ui/hooks'

export default function ApiKeysSection({ state, loading }: { state: DemoState; loading: boolean }) {
  const now = useNow()
  return (
    <div className="stack">
      <div>
        <h2 className="card-title">API keys</h2>
        <p className="card-subtitle">Each agent signs its requests with its own key. Only the first characters are kept.</p>
      </div>

      <div className="notice tone-info">
        <Info size={18} aria-hidden="true" />
        <p>
          A full key is shown once, when it's created. To rotate or revoke a key, open the agent.
        </p>
      </div>

      <div className="st-table-card">
        {loading ? (
          <SkeletonRows rows={4} />
        ) : state.agents.length === 0 ? (
          <EmptyState
            title="No agents yet"
            action={
              <Link to="/app/agents" className="btn btn-primary">
                Register an agent
              </Link>
            }
          >
            Register an agent to create its first API key.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <caption className="visually-hidden">API keys by agent</caption>
              <thead>
                <tr>
                  <th scope="col">Agent</th>
                  <th scope="col">Key</th>
                  <th scope="col">Key status</th>
                  <th scope="col">Agent status</th>
                  <th scope="col">Last used</th>
                  <th scope="col">
                    <span className="visually-hidden">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {state.agents.map((agent) => {
                  const revoked = !agent.api_key_prefix
                  return (
                    <tr key={agent.id} className="row-link">
                      <td>
                        <Link to={`/app/agents/${agent.id}`} className="row-anchor">
                          {agent.name}
                        </Link>
                      </td>
                      <td className="mono">{revoked ? <span className="muted">—</span> : `${agent.api_key_prefix}…`}</td>
                      <td>
                        {revoked ? (
                          <Badge tone="deny" icon="✕">
                            Revoked
                          </Badge>
                        ) : (
                          <Badge tone="allow" icon="✓">
                            Active
                          </Badge>
                        )}
                      </td>
                      <td>
                        <AgentStatusBadge status={agent.status} />
                      </td>
                      <td>
                        {agent.last_used_at ? (
                          <time dateTime={agent.last_used_at} title={formatTimestamp(agent.last_used_at)}>
                            {timeAgo(agent.last_used_at, now)}
                          </time>
                        ) : (
                          <span className="muted">Never</span>
                        )}
                      </td>
                      <td className="st-manage" aria-hidden="true">
                        Manage →
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
