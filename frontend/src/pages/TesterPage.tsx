import { useState } from 'react'
import { Link } from 'react-router'
import type { SpendRequest } from '../api/spendRequests'
import DecisionCard from '../components/DecisionCard'
import SpendRequestForm from '../components/SpendRequestForm'
import { useSession } from '../session/context'

export default function TesterPage() {
  const { remember } = useSession()
  const [result, setResult] = useState<SpendRequest | null>(null)

  function handleResult(request: SpendRequest) {
    setResult(request)
    remember(request)
  }

  return (
    <>
      <div className="page-intro">
        <h2>Test a payment</h2>
        <p>Send a payment as an agent and see what AgentGate decides.</p>
      </div>

      <div className="tester">
        <SpendRequestForm onResult={handleResult} />
        {result ? (
          <DecisionCard
            request={result}
            actions={
              <Link to={`/requests/${result.id}`} className="text-link">
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
