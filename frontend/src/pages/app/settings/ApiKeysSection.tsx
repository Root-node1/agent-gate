import { Info } from 'lucide-react'
import EmptyState, { SkeletonRows } from '../../../ui/EmptyState'

export default function ApiKeysSection({ loading }: { loading: boolean }) {
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
        ) : (
          <EmptyState
            title="No API keys yet"
          >
            Register an agent to get an API key.
          </EmptyState>
        )}
      </div>
    </div>
  )
}
