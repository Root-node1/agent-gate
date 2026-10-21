import { useId, useRef, useState, type RefObject } from 'react'
import { Link, useParams } from 'react-router'
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CircleCheck,
  CircleX,
  Clock,
  Hourglass,
  SearchX,
  ShieldAlert,
  X,
} from 'lucide-react'
import { DemoError, decideApproval, useDemoState } from '../../demo/store'
import {
  agentById,
  budgetUsage,
  policyForAgent,
  requestById,
  riskIndicators,
  timelineForRequest,
} from '../../demo/selectors'
import type { Approval, DemoState, SpendRequest } from '../../demo/types'
import PageHeader from '../../ui/PageHeader'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import Modal from '../../ui/Modal'
import Meter from '../../ui/Meter'
import ReasonList, { RiskList } from '../../ui/ReasonList'
import Timeline from '../../ui/Timeline'
import { AgentStatusBadge, ApprovalStatus, PaymentStatusBadge } from '../../ui/StatusBadges'
import { formatDateTime, formatMoney, shortId, timeAgo } from '../../ui/format'
import { useNow, useSimulatedLoad } from '../../ui/hooks'
import { PAYMENT, SOURCE } from '../../ui/labels'
import { useToast } from '../../ui/toast-context'
import { effectiveOutcome, expiresIn, highRisk, mainRisk, personName, whySentences } from './approvals/helpers'
import './ApprovalsPage.css'

const BACK = { to: '/app/approvals', label: 'Approvals' }

export default function ApprovalDetailPage() {
  const { id } = useParams()
  const state = useDemoState()
  const now = useNow(15_000)
  const loading = useSimulatedLoad()

  if (loading) {
    return (
      <div className="stack-lg">
        <PageHeader title="Loading approval…" back={BACK} />
        <div className="card">
          <SkeletonRows rows={3} />
        </div>
        <div className="card">
          <SkeletonRows rows={5} />
        </div>
      </div>
    )
  }

  const approval = state.approvals.find((a) => String(a.id) === id)
  const request = approval && requestById(state, approval.spend_request_id)
  if (!approval || !request) {
    return (
      <div className="stack-lg">
        <PageHeader title="Approval not found" back={BACK} />
        <div className="card">
          <EmptyState
            icon={<SearchX size={24} />}
            title="We could not find this approval"
            action={
              <Link to="/app/approvals" className="btn btn-primary">
                Back to the queue
              </Link>
            }
          >
            The link may be wrong, or the demo was reset since it was shared.
          </EmptyState>
        </div>
      </div>
    )
  }

  return <ApprovalDetail state={state} approval={approval} request={request} now={now} />
}

function ApprovalDetail({
  state,
  approval,
  request,
  now,
}: {
  state: DemoState
  approval: Approval
  request: SpendRequest
  now: number
}) {
  const outcome = effectiveOutcome(approval, now)
  const agent = agentById(state, request.agent_id)
  const policy = policyForAgent(state, request.agent_id)
  const usage = budgetUsage(state, request.agent_id)
  const indicators = riskIndicators(state, request)
  const risky = highRisk(indicators)
  const amount = formatMoney(request.amount, request.currency)
  const outcomeRef = useRef<HTMLHeadingElement>(null)

  return (
    <div className="stack-lg">
      <PageHeader
        title={`${amount} to ${request.merchant}`}
        back={BACK}
        description={
          <span className="ap-header-meta">
            <ApprovalStatus outcome={outcome} />
            <span>
              Requested by {agent?.name ?? 'an unknown agent'}{' '}
              <time dateTime={request.created_at} title={formatDateTime(request.created_at)}>
                {timeAgo(request.created_at, now)}
              </time>
            </span>
          </span>
        }
        actions={
          <Link to={`/app/transactions/${request.id}`} className="btn btn-secondary">
            View transaction
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        }
      />

      <div className="split">
        <section className={`card ap-why ${risky ? 'ap-why-risky' : ''}`} aria-labelledby="ap-why-title">
          <div className="ap-why-head">
            <ShieldAlert size={22} aria-hidden="true" />
            <h2 id="ap-why-title" className="card-title">
              {outcome === 'pending' ? 'Why this needs you' : 'Why this needed a person'}
            </h2>
          </div>
          <ul className="ap-why-list">
            {whySentences(state, request).map((sentence) => (
              <li key={sentence}>{sentence}</li>
            ))}
          </ul>
          {risky && (
            <div className="notice tone-deny ap-why-alert" role="note">
              <AlertTriangle size={18} aria-hidden="true" />
              <div>
                <strong>High risk.</strong> {indicators.find((i) => i.level === 'high')?.label}. If in doubt,
                deny it: the agent can ask again.
              </div>
            </div>
          )}
          <dl className="kv ap-why-facts">
            <dt>Amount</dt>
            <dd className="ap-strong">{amount}</dd>
            <dt>Merchant</dt>
            <dd className="ap-strong">{request.merchant}</dd>
            <dt>Purpose</dt>
            <dd>{request.purpose || <span className="muted">No purpose given</span>}</dd>
            <dt>Instruction from</dt>
            <dd>
              <SourceValue source={request.source} />
            </dd>
          </dl>
        </section>

        {outcome === 'pending' ? (
          <DecisionPanel
            state={state}
            approval={approval}
            request={request}
            now={now}
            onDecided={() => requestAnimationFrame(() => outcomeRef.current?.focus())}
          />
        ) : (
          <OutcomePanel state={state} approval={approval} request={request} outcome={outcome} headingRef={outcomeRef} />
        )}
      </div>

      <div className="split">
        <div className="stack-lg">
          <section className="card" aria-labelledby="ap-rules-title">
            <div className="card-header">
              <h2 id="ap-rules-title" className="card-title">
                Rules that flagged it
              </h2>
            </div>
            <ReasonList reasons={request.reasons} />
          </section>

          <section className="card" aria-labelledby="ap-risk-title">
            <div className="card-header">
              <div>
                <h2 id="ap-risk-title" className="card-title">
                  Risk signals
                </h2>
                <p className="card-subtitle">Hints for reviewers. They do not change the decision on their own.</p>
              </div>
            </div>
            <RiskList indicators={indicators} />
          </section>

          <section className="card" aria-labelledby="ap-timeline-title">
            <div className="card-header">
              <h2 id="ap-timeline-title" className="card-title">
                Timeline
              </h2>
              <Link to={`/app/transactions/${request.id}`} className="card-link">
                Transaction {shortId(request.id)}
              </Link>
            </div>
            <Timeline state={state} events={timelineForRequest(state, request.id)} />
          </section>
        </div>

        <section className="card" aria-labelledby="ap-context-title">
          <div className="card-header">
            <h2 id="ap-context-title" className="card-title">
              Agent and policy
            </h2>
          </div>
          {agent ? (
            <div className="stack">
              <div className="ap-agent-row">
                <Link to={`/app/agents/${agent.id}`} className="ap-strong">
                  {agent.name}
                </Link>
                <AgentStatusBadge status={agent.status} />
              </div>
              {agent.description && <p className="muted small">{agent.description}</p>}
              {usage && (
                <>
                  <Meter label="Spent today" used={usage.today} limit={usage.dailyBudget} currency={usage.currency} />
                  <Meter
                    label="Spent this month"
                    used={usage.month}
                    limit={usage.monthlyBudget}
                    currency={usage.currency}
                  />
                </>
              )}
              {policy && (
                <>
                  <dl className="kv">
                    <dt>Needs a person above</dt>
                    <dd className="num ap-num-left">{formatMoney(policy.approval_threshold, policy.currency)}</dd>
                    <dt>Never pays above</dt>
                    <dd className="num ap-num-left">{formatMoney(policy.per_transaction_cap, policy.currency)}</dd>
                    <dt>This request</dt>
                    <dd className="num ap-num-left ap-strong">{amount}</dd>
                  </dl>
                  <Link to={`/app/policies/${policy.id}`} className="card-link">
                    View {policy.name}
                  </Link>
                </>
              )}
            </div>
          ) : (
            <p className="hint">This agent no longer exists.</p>
          )}
        </section>
      </div>
    </div>
  )
}

function SourceValue({ source }: { source: SpendRequest['source'] }) {
  if (source === 'trusted') return <span>{SOURCE.trusted.label}</span>
  return (
    <span className={`pill pill-solid ${source === 'untrusted' ? 'tone-deny' : 'tone-approval'} ap-source`}>
      <AlertTriangle size={14} aria-hidden="true" />
      {SOURCE[source].label}
    </span>
  )
}

function DecisionPanel({
  state,
  approval,
  request,
  now,
  onDecided,
}: {
  state: DemoState
  approval: Approval
  request: SpendRequest
  now: number
  onDecided: () => void
}) {
  const toast = useToast()
  const noteId = useId()
  const [note, setNote] = useState('')
  const [confirming, setConfirming] = useState<'approved' | 'denied' | null>(null)
  const [error, setError] = useState('')
  const expiry = expiresIn(approval.expires_at, now)
  const risk = mainRisk(state, request)
  const agent = agentById(state, request.agent_id)
  const amount = formatMoney(request.amount, request.currency)

  function open(choice: 'approved' | 'denied') {
    setError('')
    setConfirming(choice)
  }

  function confirm() {
    if (!confirming) return
    try {
      decideApproval(approval.id, confirming, note)
      setConfirming(null)
      toast.show(
        confirming === 'approved'
          ? `Approved. Sending ${amount} to ${request.merchant} through PayPal.`
          : `Denied. ${request.merchant} will not be paid.`,
      )
      onDecided()
    } catch (e) {
      setError(e instanceof DemoError ? e.message : 'Something went wrong. Please try again.')
    }
  }

  const approving = confirming === 'approved'

  return (
    <section className="card ap-decide" aria-labelledby="ap-decide-title">
      <div className="card-header">
        <h2 id="ap-decide-title" className="card-title">
          Your decision
        </h2>
        <span className={`ap-expiry ${expiry.urgent ? 'ap-expiry-urgent' : ''}`}>
          <Clock size={14} aria-hidden="true" />
          {expiry.text}
        </span>
      </div>
      <p className="muted small">
        Approving sends the payment to PayPal right away. Denying blocks it; the agent is told and nothing is paid.
      </p>
      <div className="field">
        <label htmlFor={noteId}>Note for the audit log (optional)</label>
        <textarea
          id={noteId}
          rows={3}
          value={note}
          maxLength={500}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. Checked the invoice with the vendor"
        />
      </div>
      <div className="ap-decide-actions">
        <button type="button" className="btn btn-success" onClick={() => open('approved')}>
          <Check size={18} aria-hidden="true" />
          Approve
        </button>
        <button type="button" className="btn btn-danger" onClick={() => open('denied')}>
          <X size={18} aria-hidden="true" />
          Deny
        </button>
      </div>

      <Modal
        open={confirming !== null}
        onClose={() => setConfirming(null)}
        title={approving ? 'Approve this payment?' : 'Deny this payment?'}
        footer={
          error ? (
            <button type="button" className="btn btn-secondary" onClick={() => setConfirming(null)}>
              Close
            </button>
          ) : (
            <>
              <button type="button" className="btn btn-secondary" onClick={() => setConfirming(null)}>
                Cancel
              </button>
              <button type="button" className={`btn ${approving ? 'btn-success' : 'btn-danger'}`} onClick={confirm}>
                {approving ? <Check size={18} aria-hidden="true" /> : <X size={18} aria-hidden="true" />}
                {approving ? `Approve ${amount}` : 'Deny payment'}
              </button>
            </>
          )
        }
      >
        <div className="stack">
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <p>
            {approving
              ? 'AgentGate will send this payment to PayPal now. This cannot be undone here.'
              : 'The payment will be blocked and the agent told why.'}
          </p>
          <dl className="kv">
            <dt>Amount</dt>
            <dd className="ap-strong">{amount}</dd>
            <dt>Merchant</dt>
            <dd className="ap-strong">{request.merchant}</dd>
            <dt>Agent</dt>
            <dd>{agent?.name ?? '—'}</dd>
            <dt>Note</dt>
            <dd>{note.trim() || <span className="muted">No note</span>}</dd>
          </dl>
          <div className={`notice ${risk.high ? 'tone-deny' : 'tone-approval'} ap-modal-risk`}>
            <AlertTriangle size={18} aria-hidden="true" />
            <div>
              <strong>{risk.high ? 'Main risk: ' : 'Flagged because: '}</strong>
              {risk.text}
            </div>
          </div>
        </div>
      </Modal>
    </section>
  )
}

function OutcomePanel({
  state,
  approval,
  request,
  outcome,
  headingRef,
}: {
  state: DemoState
  approval: Approval
  request: SpendRequest
  outcome: 'approved' | 'denied' | 'expired'
  headingRef: RefObject<HTMLHeadingElement | null>
}) {
  const Icon = outcome === 'approved' ? CircleCheck : outcome === 'denied' ? CircleX : Hourglass
  const title = outcome === 'approved' ? 'Approved' : outcome === 'denied' ? 'Denied' : 'Expired'
  const when = outcome === 'expired' ? approval.expires_at : (approval.decided_at ?? approval.created_at)

  return (
    <section className={`card ap-outcome-card ap-outcome-${outcome}`} aria-labelledby="ap-outcome-title">
      <div className="ap-why-head">
        <Icon size={22} aria-hidden="true" />
        <h2 id="ap-outcome-title" className="card-title" ref={headingRef} tabIndex={-1}>
          {title}
        </h2>
      </div>
      {outcome === 'expired' ? (
        <p className="small">
          Nobody decided in time, so the payment was not sent. The agent has to send a new request.
        </p>
      ) : null}
      <dl className="kv">
        {outcome !== 'expired' && (
          <>
            <dt>By</dt>
            <dd>{personName(state, approval.approver)}</dd>
          </>
        )}
        <dt>{outcome === 'expired' ? 'Expired' : 'When'}</dt>
        <dd>
          <time dateTime={when}>{formatDateTime(when)}</time>
        </dd>
        {outcome !== 'expired' && (
          <>
            <dt>Note</dt>
            <dd>{approval.note || <span className="muted">No note</span>}</dd>
          </>
        )}
        <dt>Payment</dt>
        <dd aria-live="polite" className="ap-payment">
          <PaymentStatusBadge status={request.payment_status} />
          <span className="muted small">{PAYMENT[request.payment_status].summary}</span>
        </dd>
        {request.paypal_reference && (
          <>
            <dt>PayPal reference</dt>
            <dd className="mono">{request.paypal_reference}</dd>
          </>
        )}
      </dl>
    </section>
  )
}
