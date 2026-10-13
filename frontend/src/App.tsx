import { useEffect, useState } from 'react'

export default function App() {
  const [status, setStatus] = useState('checking...')

  useEffect(() => {
    fetch('/api/health/')
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('backend unreachable'))
  }, [])

  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>AgentGate</h1>
      <p>Backend status: {status}</p>
    </main>
  )
}
