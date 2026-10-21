import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { Bot, KeyRound, Pause, Play, RefreshCw, ShieldOff, Trash2 } from 'lucide-react'
import { DemoError, revokeKey, rotateKey, setAgentStatus, useDemoState } from '../../demo/store'
import { agentById, budgetUsage, decisionTotals, policyForAgent } from '../../demo/selectors'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import { describeEvent } from '../../ui/events'
import { formatDate, formatDateTime, formatMoney, shortId, timeAgo } from '../../ui/format'
import { useNow, useSimulatedLoad } from '../../ui/hooks'
import { DECISION, EVENT } from '../../ui/labels'
import Meter from '../../ui/Meter'
import Modal from '../../ui/Modal'
import PageHeader from '../../ui/PageHeader'
import { AgentStatusBadge, DecisionStatus, PaymentStatusBadge } from '../../ui/StatusBadges'
import { useToast } from '../../ui/toast-context'
import KeyReveal from './agents/KeyReveal'
import './AgentsPage.css'

type Dialog = null | 'suspend' | 'reactivate' | 'revoke' | 'rotate' | { rawKey: string }

const HISTORY_ROWS = 8
const EVENT_ROWS = 8

export default function AgentDetailPage() {
  const { id } = useParams()
  const state = useDemoState()
  const loading = useSimulatedLoad()
  const now = useNow()
  const toast = useToast()
  const [dialog, setDialog] = useState<Dialog>(null)
  const [error, setError] = useState<string | null>(null)

  const agent = agentById(state, Number(id))

  if (loading) {
    return (
      <div className="stack-lg" aria-busy="true">
        <div className="skeleton ag-title-skeleton" />
        <div className="split ag-split">
          <div className="card">
            <SkeletonRows rows={6} />
          </div>
          <div className="card">
            <SkeletonRows rows={4} />
          </div>
        </div>
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="stack-lg">
        <PageHeader title="Agent not found" back={{ to: '/app/agents', label: 'Agents' }} />
        <div className="card">
          <EmptyState
            icon={<Bot size={24} />}
            title="We couldn't find this agent"
            action={
              <Link to="/app/agents" className="btn btn-primary">
                See all agents
              </Link>
            }
          >
            It may have been removed, or the link is wrong.
          </EmptyState>
        </div>
      </div>
    )
  }

  const policy = policyForAgent(state, agent.id)
  const usage = budgetUsage(state, agent.id, new Date(now))
  const requests = state.requests.filter((r) => r.agent_id === agent.id)
  const totals = decisionTotals(requests)
  const events = state.events.filter((e) => e.agent_id === agent.id).slice(0, EVENT_ROWS)
  const suspended = agent.status === 'suspended'
  const hasKey = Boolean(agent.api_key_prefix)
  const agentId = agent.id

  function run(action: () => void, message: string) {
    try {
      action()
      setDialog(null)
      setError(null)
      toast.show(message, 'success')
    } catch (err) {
      setError(err instanceof DemoError ? err.message : 'Something went wrong. Try again.')
    }
  }

  function rotate() {
    try {
      const rawKey = rotateKey(agentId)
      setDialog({ rawKey })
      setError(null)
      toast.show('New API key created. The old key no longer works.', 'success')
    } catch (err) {
      setError(err instanceof DemoError ? err.message : 'Could not create a key. Try again.')
    }
  }

  function closeDialog() {
    setDialog(null)
    setError(null)
  }

  // A dialog that closes because another one replaced it still fires its native
  // close event, so only clear the state if it still belongs to that dialog.
  function closeIf(match: (d: Dialog) => boolean) {
    return () => {
      setDialog((d) => (match(d) ? null : d))
      setError(null)
    }
  }

  const totalItems = [
    { key: 'total', label: 'Requests', value: totals.total, tone: 'neutral', icon: '' },
    { key: 'allow', label: DECISION.allow.label, value: totals.allow, tone: 'allow', icon: DECISION.allow.icon },
    {
      key: 'needs_approval',
      label: DECISION.needs_approval.label,
      value: totals.needs_approval,
      tone: 'approval',
      icon: DECISION.needs_approval.icon,
    },
    { key: 'deny', label: DECISION.deny.label, value: totals.deny, tone: 'deny', icon: DECISION.deny.icon },
  ]

  return (
    <div className="stack-lg">
      <PageHeader
        title={agent.name}
        back={{ to: '/app/agents', label: 'Agents' }}
        description={
          <span className="ag-title-row">
            <AgentStatusBadge status={agent.status} />
            <span>{agent.description || 'No description.'}</span>
          </span>
        }
        actions={
          <>
            {policy && (
              <Link to={`/app/policies/${policy.id}`} className="btn btn-secondary">
                Edit spending rules
              </Link>
            )}
            {suspended ? (
              <button type="button" className="btn btn-success" onClick={() => setDialog('reactivate')}>
                <Play size={18} aria-hidden="true" />
                Reactivate
              </button>
            ) : (
              <button type="button" className="btn btn-danger-outline" onClick={() => setDialog('suspend')}>
                <Pause size={18} aria-hidden="true" />
                Suspend agent
              </button>
            )}
          </>
        }
      />

      {suspended && (
        <div className="notice tone-deny" role="status">
          <ShieldOff size={20} aria-hidden="true" />
          <div>
            <strong>This agent is suspended.</strong> AgentGate rejects every request it sends until you reactivate it.
          </div>
        </div>
      )}
      {!suspended && !hasKey && (
        <div className="notice tone-approval" role="status">
          <KeyRound size={20} aria-hidden="true" />
          <div>
            <strong>This agent has no API key.</strong> It cannot make requests until you create a new key.
          </div>
        </div>
      )}

      <div className="split ag-split">
        <div className="stack-lg">
          <section className="card" aria-labelledby="ag-spend-title">
            <div className="card-header">
              <div>
                <h2 id="ag-spend-title" className="card-title">
                  Spending
                </h2>
                <p className="card-subtitle">
                  Counts allowed payments plus approvals that are waiting or approved.
                </p>
              </div>
            </div>
            <div className="stack">
              {usage ? (
                <div className="grid grid-2">
                  <Meter label="Today" used={usage.today} limit={usage.dailyBudget} currency={usage.currency} />
                  <Meter
                    label="This month"
                    used={usage.month}
                    limit={usage.monthlyBudget}
                    currency={usage.currency}
                  />
                </div>
              ) : (
                <p className="hint">No policy, so no budgets are set.</p>
              )}
              <dl className="ag-totals" aria-label="Decisions for all requests">
                {totalItems.map((item) => (
                  <div key={item.key} className={`ag-total tone-${item.tone}`}>
                    <dt>
                      {item.icon && <span aria-hidden="true">{item.icon}</span>}
                      {item.label}
                    </dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </section>

          <section className="card card-flush" aria-labelledby="ag-history-title">
            <div className="card-header">
              <div>
                <h2 id="ag-history-title" className="card-title">
                  Recent requests
                </h2>
                <p className="card-subtitle">Latest payments this agent asked for.</p>
              </div>
              {requests.length > 0 && (
                <Link to={`/app/transactions?agent=${agent.id}`} className="card-link">
                  View all {requests.length}
                </Link>
              )}
            </div>
            {requests.length === 0 ? (
              <EmptyState title="No requests yet">
                Requests appear here once the agent calls <code>POST /v1/spend-requests/</code> with its key.
              </EmptyState>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Merchant</th>
                      <th scope="col" className="num">
                        Amount
                      </th>
                      <th scope="col">Decision</th>
                      <th scope="col">Payment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {requests.slice(0, HISTORY_ROWS).map((r) => (
                      <tr key={r.id} className="row-link">
                        <td>
                          <Link to={`/app/transactions/${r.id}`} className="row-anchor">
                            {r.merchant}
                          </Link>
                          <span className="ag-sub">
                            <time dateTime={r.created_at} title={formatDateTime(r.created_at)}>
                              {timeAgo(r.created_at, now)}
                            </time>{' '}
                            · <span className="mono">{shortId(r.id)}</span>
                          </span>
                        </td>
                        <td className="num ag-nowrap">{formatMoney(r.amount, r.currency)}</td>
                        <td>
                          <DecisionStatus decision={r.decision} />
                        </td>
                        <td>
                          <PaymentStatusBadge status={r.payment_status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <div className="stack-lg">
          <section className="card" aria-labelledby="ag-key-title">
            <div className="card-header">
              <h2 id="ag-key-title" className="card-title">
                API key
              </h2>
            </div>
            <dl className="kv">
              <dt>Key</dt>
              <dd>
                {hasKey ? (
                  <span className="mono">{agent.api_key_prefix}…</span>
                ) : (
                  <span className="ag-nokey">
                    <KeyRound size={14} aria-hidden="true" /> Revoked
                  </span>
                )}
              </dd>
              <dt>Agent created</dt>
              <dd>{formatDate(agent.created_at)}</dd>
              <dt>Last used</dt>
              <dd>
                {agent.last_used_at ? (
                  <time dateTime={agent.last_used_at} title={formatDateTime(agent.last_used_at)}>
                    {timeAgo(agent.last_used_at, now)}
                  </time>
                ) : (
                  'Never'
                )}
              </dd>
            </dl>
            <p className="hint ag-key-note">
              Only the first 8 characters are stored. The full key was shown once, when it was created.
            </p>
            <div className="ag-key-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setDialog('rotate')}>
                <RefreshCw size={16} aria-hidden="true" />
                Create new key
              </button>
              {hasKey && (
                <button type="button" className="btn btn-danger-outline" onClick={() => setDialog('revoke')}>
                  <Trash2 size={16} aria-hidden="true" />
                  Revoke key
                </button>
              )}
            </div>
          </section>

          <section className="card" aria-labelledby="ag-policy-title">
            <div className="card-header">
              <h2 id="ag-policy-title" className="card-title">
                Spending rules
              </h2>
              {policy && (
                <Link to={`/app/policies/${policy.id}`} className="card-link">
                  Edit
                </Link>
              )}
            </div>
            {policy ? (
              <dl className="kv">
                <dt>Policy</dt>
                <dd>{policy.name}</dd>
                <dt>Needs approval above</dt>
                <dd>{formatMoney(policy.approval_threshold, policy.currency)}</dd>
                <dt>Blocked above</dt>
                <dd>{formatMoney(policy.per_transaction_cap, policy.currency)}</dd>
                <dt>Merchants</dt>
                <dd>
                  {policy.allowed_merchants.length
                    ? `Only ${policy.allowed_merchants.length} allowed`
                    : 'Any merchant'}
                  {policy.blocked_merchants.length ? `, ${policy.blocked_merchants.length} blocked` : ''}
                </dd>
              </dl>
            ) : (
              <p className="hint">No policy assigned.</p>
            )}
          </section>

          <section className="card card-flush" aria-labelledby="ag-events-title">
            <div className="card-header">
              <h2 id="ag-events-title" className="card-title">
                Recent activity
              </h2>
              <Link to="/app/audit" className="card-link">
                Audit log
              </Link>
            </div>
            {events.length === 0 ? (
              <EmptyState title="No events yet" />
            ) : (
              <ul className="ag-events">
                {events.map((e) => {
                  const info = EVENT[e.event_type]
                  return (
                    <li key={e.id}>
                      <span className="ag-event-title">
                        <strong className={`tone-${info.tone}`}>
                          <span className="ag-event-dot" aria-hidden="true" />
                          <Link to={`/app/audit?event=${e.id}`}>{info.label}</Link>
                        </strong>
                        <time className="small muted" dateTime={e.created_at} title={formatDateTime(e.created_at)}>
                          {timeAgo(e.created_at, now)}
                        </time>
                      </span>
                      <span className="muted">{describeEvent(state, e)}</span>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>
      </div>

      <Modal
        open={dialog === 'suspend'}
        onClose={closeIf((d) => d === 'suspend')}
        title={`Suspend ${agent.name}?`}
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={closeDialog}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => run(() => setAgentStatus(agent.id, 'suspended'), `${agent.name} suspended.`)}
            >
              Suspend agent
            </button>
          </>
        }
      >
        {error && <p className="form-error" role="alert">{error}</p>}
        <p>While suspended:</p>
        <ul className="ag-confirm-list">
          <li>AgentGate rejects every request it sends. Nothing is paid.</li>
          <li>Its API key and policy are kept, so you can reactivate it later.</li>
          <li>Payments already approved or sent are not affected.</li>
        </ul>
      </Modal>

      <Modal
        open={dialog === 'reactivate'}
        onClose={closeIf((d) => d === 'reactivate')}
        title={`Reactivate ${agent.name}?`}
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={closeDialog}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-success"
              onClick={() => run(() => setAgentStatus(agent.id, 'active'), `${agent.name} is active again.`)}
            >
              Reactivate
            </button>
          </>
        }
      >
        {error && <p className="form-error" role="alert">{error}</p>}
        <p>
          The agent can send requests again{hasKey ? ' with its current key' : ' once you create a key'}. Every
          request is still checked against its spending rules.
        </p>
      </Modal>

      <Modal
        open={dialog === 'revoke'}
        onClose={closeIf((d) => d === 'revoke')}
        title="Revoke this API key?"
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={closeDialog}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => run(() => revokeKey(agent.id), `Key ${agent.api_key_prefix}… revoked.`)}
            >
              Revoke key
            </button>
          </>
        }
      >
        {error && <p className="form-error" role="alert">{error}</p>}
        <p>
          Key <span className="mono">{agent.api_key_prefix}…</span> stops working right away.
        </p>
        <ul className="ag-confirm-list">
          <li>{agent.name} can no longer make requests. Any call with this key is rejected.</li>
          <li>This cannot be undone. To reconnect the agent, create a new key.</li>
        </ul>
      </Modal>

      <Modal
        open={dialog === 'rotate'}
        onClose={closeIf((d) => d === 'rotate')}
        title="Create a new API key?"
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={closeDialog}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={rotate}>
              Create new key
            </button>
          </>
        }
      >
        {error && <p className="form-error" role="alert">{error}</p>}
        {hasKey ? (
          <p>
            The current key <span className="mono">{agent.api_key_prefix}…</span> stops working as soon as the new
            one is created. Update the agent right after.
          </p>
        ) : (
          <p>{agent.name} gets a new key. It is shown once, so have somewhere safe to store it.</p>
        )}
      </Modal>

      <Modal
        open={typeof dialog === 'object' && dialog !== null}
        onClose={closeIf((d) => typeof d === 'object')}
        title="Save your new API key"
        className="modal-wide"
        footer={
          <button type="button" className="btn btn-primary" onClick={closeDialog}>
            I've saved it
          </button>
        }
      >
        {typeof dialog === 'object' && dialog !== null && <KeyReveal agentName={agent.name} rawKey={dialog.rawKey} />}
      </Modal>
    </div>
  )
}
