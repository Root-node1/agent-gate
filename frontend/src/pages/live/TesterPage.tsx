import { useState } from 'react'
import { Link } from 'react-router'
import type { SpendRequest } from '../../api/spendRequests'
import DecisionCard from '../../components/DecisionCard'
import SpendRequestForm from '../../components/SpendRequestForm'
import { useSession } from '../../session/context'
import PageHeader from '../../ui/PageHeader'

export default function TesterPage() {
  const { remember } = useSession()
  const [result, setResult] = useState<SpendRequest | null>(null)

  function handleResult(request: SpendRequest) {
    setResult(request)
    remember(request)
  }

  return (
    <>
      <PageHeader
        title="Live API tester"
        description="Send a real request to the AgentGate backend as an agent and see what it decides. Needs the backend running and an agent key."
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
