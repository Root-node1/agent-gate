import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError, getSpendRequest, isRequestId, type SpendRequest } from '../api/spendRequests'
import AgentKeyField from '../components/AgentKeyField'
import DecisionCard from '../components/DecisionCard'
import { useSession } from '../session/context'

interface Loaded {
  /** Which fetch this result belongs to, so a stale result is never shown. */
  key: string
  request?: SpendRequest
  error?: string
}

export default function RequestDetailPage() {
  const { id = '' } = useParams()
  const { agentKey, remember } = useSession()
  const [reloads, setReloads] = useState(0)
  const [loaded, setLoaded] = useState<Loaded | null>(null)

  const validId = isRequestId(id)
  const fetchKey = `${id}|${agentKey}|${reloads}`

  useEffect(() => {
    if (!validId || !agentKey) return
    let cancelled = false
    getSpendRequest(agentKey, id).then(
      (request) => {
        if (cancelled) return
        setLoaded({ key: fetchKey, request })
        remember(request)
      },
      (err) => {
        if (cancelled) return
        const message = err instanceof ApiError ? err.message : 'Something went wrong. Try again.'
        setLoaded({ key: fetchKey, error: message })
      },
    )
    return () => {
      cancelled = true
    }
  }, [validId, agentKey, id, fetchKey, remember])

  const current = loaded?.key === fetchKey ? loaded : null
  // Keep showing the last request while refreshing, so the card does not flicker.
  const shown = current?.request ?? (loaded?.request?.id === id ? loaded.request : undefined)

  let body
  if (!validId) {
    body = <p className="form-error">This link has a broken request ID.</p>
  } else if (!agentKey) {
    body = (
      <div className="panel">
        <p className="hint key-prompt">Paste the agent key that sent this request.</p>
        <AgentKeyField />
      </div>
    )
  } else if (current?.error) {
    body = (
      <p className="form-error" role="alert">
        {current.error}
      </p>
    )
  } else if (shown) {
    body = (
      <DecisionCard
        request={shown}
        actions={
          <button
            type="button"
            className="button button-secondary"
            onClick={() => setReloads((n) => n + 1)}
            disabled={!current}
          >
            {current ? 'Refresh status' : 'Refreshing…'}
          </button>
        }
      />
    )
  } else {
    body = <p className="panel empty">Loading request…</p>
  }

  return (
    <>
      <Link to="/requests" className="text-link back-link">
        ← All requests
      </Link>
      <div className="page-intro">
        <h2>Request</h2>
        <p>
          <code>{id}</code>
        </p>
      </div>
      <div className="detail">{body}</div>
    </>
  )
}
