import { useEffect, useState } from 'react'
import type { SpendRequest } from './api/spendRequests'
import DecisionCard from './components/DecisionCard'
import Logo from './components/Logo'
import SpendRequestForm from './components/SpendRequestForm'

export default function App() {
  const [status, setStatus] = useState('checking...')
  const [result, setResult] = useState<SpendRequest | null>(null)

  useEffect(() => {
    fetch('/api/health/')
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('backend unreachable'))
  }, [])

  return (
    <>
      <header className="app-header">
        <h1>
          <Logo />
        </h1>
        <p className="health">Backend: {status}</p>
      </header>

      <main className="page">
        <div className="page-intro">
          <h2>Test a payment</h2>
          <p>Send a payment as an agent and see what AgentGate decides.</p>
        </div>

        <div className="tester">
          <SpendRequestForm onResult={setResult} />
          {result ? (
            <DecisionCard request={result} />
          ) : (
            <section className="panel empty">
              <p>The decision will show here.</p>
            </section>
          )}
        </div>
      </main>
    </>
  )
}
