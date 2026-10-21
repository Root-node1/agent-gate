import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { isRequestId } from '../api/spendRequests'
import DecisionBadge from '../components/DecisionBadge'
import { formatTime } from '../components/labels'
import { useSession } from '../session/context'

export default function RequestsPage() {
  const { recent } = useSession()
  const navigate = useNavigate()
  const [id, setId] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = id.trim()
    if (!isRequestId(trimmed)) {
      setError('That is not a request ID. It looks like 26e5edc7-4f8f-420d-b1bd-596355f02e2b.')
      return
    }
    navigate(`/requests/${trimmed}`)
  }

  return (
    <>
      <div className="page-intro">
        <h2>Requests</h2>
        <p>Look up a payment request to see its decision and approval status.</p>
      </div>

      <form className="panel lookup" onSubmit={handleSubmit} noValidate>
        <div className="field">
          <label htmlFor="requestId">Request ID</label>
          <input
            id="requestId"
            placeholder="26e5edc7-4f8f-420d-b1bd-596355f02e2b"
            value={id}
            onChange={(e) => {
              setId(e.target.value)
              setError('')
            }}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? 'requestId-error' : undefined}
          />
          {error && (
            <span id="requestId-error" className="field-error">
              {error}
            </span>
          )}
        </div>
        <button className="button" type="submit">
          Look up
        </button>
      </form>

      <section className="panel">
        <h3 className="section-title">Sent from this tab</h3>
        {recent.length === 0 ? (
          <p className="hint">
            Nothing yet. Requests you send from <Link to="/">Test a payment</Link> show up here.
          </p>
        ) : (
          <ul className="request-list">
            {recent.map((request) => (
              <li key={request.id}>
                <Link to={`/requests/${request.id}`} className="request-row">
                  <DecisionBadge decision={request.decision} />
                  <span className="request-row-main">
                    <strong>
                      {request.amount} {request.currency}
                    </strong>{' '}
                    to {request.merchant}
                  </span>
                  <span className="hint">{formatTime(request.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
