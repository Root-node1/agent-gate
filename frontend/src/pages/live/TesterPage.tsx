import { useState } from 'react'
import { Link } from 'react-router'
import { useApiResource } from '../../api/useApiResource'
import type { SpendRequest } from '../../api/spendRequests'
import DecisionCard from '../../components/DecisionCard'
import SpendRequestForm from '../../components/SpendRequestForm'
import { useSession } from '../../session/context'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import PageHeader from '../../ui/PageHeader'

export default function TesterPage() {
  const { remember } = useSession()
  const resource = useApiResource(() => Promise.resolve({ ok: true }))
  const [result, setResult] = useState<SpendRequest | null>(null)

  if (resource.status === 'loading') {
    return (
      <div className="stack-lg">
        <PageHeader title="Tester" description="Loading…" />
        <section className="card"><SkeletonRows rows={4} /></section>
      </div>
    )
  }

  if (resource.status === 'error') {
    return (
      <div className="stack-lg">
        <PageHeader title="Tester" description="Failed to load" />
        <EmptyState
          title="Unable to load tester"
          action={<button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>Retry</button>}
        >
          <span role="alert">{resource.error.message}</span>
        </EmptyState>
      </div>
    )
  }

  function handleResult(request: SpendRequest) {
    setResult(request)
    remember(request)
  }

  return (
    <>
      <PageHeader
        title="Live API tester"
        description="Send a request to the AgentGate backend as an agent and see its decision. Needs the backend running and an agent key. Payment execution is separately configured and defaults to fake; confirm server settings before submitting."
        actions={
          <Link to="/app/live/requests" className="btn btn-secondary">
            Look up a request
          </Link>
        }
      />

      <div className="tester">
        <SpendRequestForm onResult={handleResult} />
        {result ? (
          <DecisionCard
            request={result}
            actions={
              <Link to={`/app/live/requests/${result.id}`} className="text-link">
                Open request page →
              </Link>
            }
          />
        ) : (
          <section className="panel empty">
            <p>The decision will show here.</p>
          </section>
        )}
      </div>
    </>
  )
}
