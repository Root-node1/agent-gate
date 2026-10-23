// In-memory demo backend. Every dashboard screen reads from this store, so a
// request submitted in the simulator shows up in the queue, transactions,
// overview and audit log at once. Nothing is persisted: reload resets it.
//
// Flow mirrors backend/gate/services.py: record the request, count spend,
// run the rule engine, store the decision, open an approval if needed, and
// write audit events at every step. Payment execution is simulated.

import { useSyncExternalStore } from 'react'
import { evaluate } from './rules'
import { buildSeed } from './seed'
import type {
  Agent,
  Approval,
  AuditEvent,
  AuditEventType,
  DemoState,
  Policy,
  SpendRequest,
  Source,
} from './types'

export class DemoError extends Error {}

/** How long a pending approval stays open before it expires. */
export const APPROVAL_TTL_MINUTES = 24 * 60

/** How long the simulated PayPal call takes. */
const PAYMENT_DELAY_MS = 2500

// Built on first use: seed.ts imports helpers from this module.
let state: DemoState | null = null
const listeners = new Set<() => void>()

function setState(update: (prev: DemoState) => DemoState) {
  state = update(getDemoState())
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getDemoState(): DemoState {
  state ??= buildSeed()
  return state
}

/** Subscribe a component to the whole demo state. */
export function useDemoState(): DemoState {
  return useSyncExternalStore(subscribe, getDemoState)
}

export function resetDemo() {
  setState(() => buildSeed())
}

// ---------------------------------------------------------------------------
// Internal helpers, shared with the seed builder through the Draft type.
// ---------------------------------------------------------------------------

/** A mutable working copy used while building one change (or the seed). */
export interface Draft {
  state: DemoState
  nextEventId: number
}

export function addEvent(
  draft: Draft,
  event_type: AuditEventType,
  fields: Partial<Omit<AuditEvent, 'id' | 'event_type'>> & { actor: string; created_at: string },
) {
  draft.state.events.unshift({
    id: draft.nextEventId++,
    event_type,
    agent_id: null,
    spend_request_id: null,
    payload: {},
    ...fields,
  })
}

function startOfDay(at: Date) {
  return new Date(at.getFullYear(), at.getMonth(), at.getDate())
}

function startOfMonth(at: Date) {
  return new Date(at.getFullYear(), at.getMonth(), 1)
}

/**
 * Money that counts against budgets: allowed requests plus approvals that are
 * pending or approved. Same rule as services.counted_spend.
 */
export function countedSpend(s: DemoState, agentId: number, currency: string, since: Date, until?: Date) {
  const approvalFor = new Map(s.approvals.map((a) => [a.spend_request_id, a]))
  return s.requests
    .filter((r) => {
      const at = new Date(r.created_at)
      if (r.agent_id !== agentId || r.currency !== currency || at < since) return false
      if (until && at > until) return false
      if (r.decision === 'allow') return true
      const outcome = approvalFor.get(r.id)?.outcome
      return r.decision === 'needs_approval' && (outcome === 'pending' || outcome === 'approved')
    })
    .reduce((sum, r) => sum + r.amount, 0)
}

export function spentWindows(s: DemoState, agentId: number, currency: string, at: Date) {
  return {
    today: countedSpend(s, agentId, currency, startOfDay(at), at),
    this_month: countedSpend(s, agentId, currency, startOfMonth(at), at),
  }
}

function randomHex(length: number) {
  const bytes = crypto.getRandomValues(new Uint8Array(length))
  return Array.from(bytes, (b) => (b % 16).toString(16)).join('')
}

export function newKey() {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
  const bytes = crypto.getRandomValues(new Uint8Array(43))
  return 'agk_' + Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('')
}

export function paypalReference() {
  return 'DEMO-' + randomHex(12).toUpperCase()
}

export interface SubmitInput {
  amount: number
  currency: string
  merchant: string
  purpose: string
  source: Source
}

/** Record one spend request at a given time. Used by the seed and by submitSpendRequest. */
export function recordRequest(
  draft: Draft,
  agent: Agent,
  input: SubmitInput,
  at: Date,
  id: string = crypto.randomUUID(),
): SpendRequest {
  const policy = draft.state.policies.find((p) => p.agent_id === agent.id)
  if (!policy) throw new DemoError(`${agent.name} has no policy configured.`)
  const created_at = at.toISOString()
  const currency = input.currency.toUpperCase()

  addEvent(draft, 'spend_request.received', {
    actor: agent.name,
    agent_id: agent.id,
    spend_request_id: id,
    created_at,
    payload: { amount: input.amount.toFixed(2), currency, merchant: input.merchant, source: input.source },
  })

  const result = evaluate(
    { ...input, currency },
    policy,
    spentWindows(draft.state, agent.id, policy.currency, at),
  )

  const request: SpendRequest = {
    id,
    agent_id: agent.id,
    amount: input.amount,
    currency,
    merchant: input.merchant,
    purpose: input.purpose,
    source: input.source,
    risk_score: 0,
    decision: result.decision,
    reasons: result.reasons.map(({ code, message }) => ({ code, message })),
    matched_rules: result.reasons.map((r) => r.code),
    payment_status:
      result.decision === 'allow'
        ? 'processing'
        : result.decision === 'needs_approval'
          ? 'awaiting_approval'
          : 'not_sent',
    paypal_reference: '',
    created_at,
  }
  draft.state.requests.unshift(request)

  addEvent(draft, 'spend_request.decided', {
    actor: 'AgentGate',
    agent_id: agent.id,
    spend_request_id: id,
    created_at,
    payload: { decision: result.decision, rules: request.matched_rules },
  })

  if (result.decision === 'needs_approval') {
    const approval: Approval = {
      id: (draft.state.approvals.reduce((max, a) => Math.max(max, a.id), 0) || 0) + 1,
      spend_request_id: id,
      outcome: 'pending',
      approver: null,
      note: '',
      created_at,
      expires_at: new Date(at.getTime() + APPROVAL_TTL_MINUTES * 60_000).toISOString(),
      decided_at: null,
    }
    draft.state.approvals.unshift(approval)
    addEvent(draft, 'approval.requested', {
      actor: 'AgentGate',
      agent_id: agent.id,
      spend_request_id: id,
      created_at,
    })
  }

  if (result.decision === 'allow') {
    addEvent(draft, 'payment.processing', {
      actor: 'AgentGate',
      agent_id: agent.id,
      spend_request_id: id,
      created_at,
    })
  }

  agent.last_used_at = created_at
  return request
}

/** Finish (or fail) the simulated PayPal payment for a request. */
export function settlePayment(draft: Draft, requestId: string, at: Date, ok = true) {
  const request = draft.state.requests.find((r) => r.id === requestId)
  if (!request || request.payment_status !== 'processing') return
  request.payment_status = ok ? 'completed' : 'failed'
  if (ok) request.paypal_reference = paypalReference()
  addEvent(draft, ok ? 'payment.completed' : 'payment.failed', {
    actor: 'PayPal',
    agent_id: request.agent_id,
    spend_request_id: request.id,
    created_at: at.toISOString(),
    payload: ok
      ? { paypal_reference: request.paypal_reference }
      : { error: 'INSTRUMENT_DECLINED: The sandbox card was declined.' },
  })
}

/** Apply a change to a deep copy of the state, then publish it. */
function mutate<T>(change: (draft: Draft) => T): T {
  const current = getDemoState()
  const draft: Draft = {
    state: structuredClone(current),
    nextEventId: current.events.reduce((max, e) => Math.max(max, e.id), 0) + 1,
  }
  const result = change(draft)
  setState(() => draft.state)
  return result
}

function schedulePayment(requestId: string) {
  setTimeout(() => mutate((draft) => settlePayment(draft, requestId, new Date())), PAYMENT_DELAY_MS)
}

function findAgent(draft: Draft, agentId: number) {
  const agent = draft.state.agents.find((a) => a.id === agentId)
  if (!agent) throw new DemoError('Agent not found.')
  return agent
}

// ---------------------------------------------------------------------------
// Public actions
// ---------------------------------------------------------------------------

/** What an AI agent does: POST /v1/spend-requests/. */
export function submitSpendRequest(agentId: number, input: SubmitInput): SpendRequest {
  const request = mutate((draft) => {
    const agent = findAgent(draft, agentId)
    if (agent.status !== 'active') throw new DemoError(`${agent.name} is suspended, so its requests are rejected.`)
    if (!agent.api_key_prefix) throw new DemoError(`${agent.name} has no API key. Create one first.`)
    return recordRequest(draft, agent, input, new Date())
  })
  if (request.decision === 'allow') schedulePayment(request.id)
  return request
}

export function decideApproval(approvalId: number, outcome: 'approved' | 'denied', note: string) {
  const approval = mutate((draft) => {
    const approval = draft.state.approvals.find((a) => a.id === approvalId)
    if (!approval) throw new DemoError('This approval no longer exists.')
    if (approval.outcome !== 'pending') {
      throw new DemoError('Someone already decided this payment. Refresh to see the outcome.')
    }
    const now = new Date()
    if (new Date(approval.expires_at) < now) {
      throw new DemoError('This approval has expired. The agent must send a new request.')
    }
    const request = draft.state.requests.find((r) => r.id === approval.spend_request_id)!
    approval.outcome = outcome
    approval.note = note.trim()
    approval.approver = draft.state.currentUser.email
    approval.decided_at = now.toISOString()
    request.payment_status = outcome === 'approved' ? 'processing' : 'not_sent'

    addEvent(draft, outcome === 'approved' ? 'approval.approved' : 'approval.denied', {
      actor: draft.state.currentUser.email,
      agent_id: request.agent_id,
      spend_request_id: request.id,
      created_at: approval.decided_at,
      payload: approval.note ? { note: approval.note } : {},
    })
    if (outcome === 'approved') {
      addEvent(draft, 'payment.processing', {
        actor: 'AgentGate',
        agent_id: request.agent_id,
        spend_request_id: request.id,
        created_at: approval.decided_at,
      })
    }
    return approval
  })
  if (outcome === 'approved') schedulePayment(approval.spend_request_id)
  return approval
}

export type PolicyChanges = Partial<
  Pick<
    Policy,
    | 'name'
    | 'currency'
    | 'per_transaction_cap'
    | 'approval_threshold'
    | 'daily_budget'
    | 'monthly_budget'
    | 'allowed_merchants'
    | 'blocked_merchants'
  >
>

/** Returns field errors, or null when saved. */
export function validatePolicy(p: Omit<Policy, 'id' | 'agent_id' | 'updated_at'>) {
  const errors: Partial<Record<keyof Policy, string>> = {}
  const money = ['per_transaction_cap', 'approval_threshold', 'daily_budget', 'monthly_budget'] as const
  for (const field of money) {
    if (!Number.isFinite(p[field]) || p[field] <= 0) errors[field] = 'Enter an amount above 0.'
  }
  if (!errors.approval_threshold && p.approval_threshold > p.per_transaction_cap) {
    errors.approval_threshold = 'Must be at or below the per-transaction cap.'
  }
  if (!errors.per_transaction_cap && p.per_transaction_cap > p.daily_budget) {
    errors.per_transaction_cap = 'Must be at or below the daily budget.'
  }
  if (!errors.daily_budget && p.daily_budget > p.monthly_budget) {
    errors.daily_budget = 'Must be at or below the monthly budget.'
  }
  if (!/^[A-Z]{3}$/.test(p.currency)) errors.currency = 'Use a 3-letter currency code.'
  const overlap = p.allowed_merchants.filter((m) => p.blocked_merchants.includes(m))
  if (overlap.length) errors.blocked_merchants = `${overlap.join(', ')} is on both lists.`
  return Object.keys(errors).length ? errors : null
}

export function updatePolicy(policyId: number, changes: PolicyChanges) {
  return mutate((draft) => {
    const policy = draft.state.policies.find((p) => p.id === policyId)
    if (!policy) throw new DemoError('Policy not found.')
    const updated = { ...policy, ...changes }
    if (validatePolicy(updated)) throw new DemoError('Fix the highlighted fields first.')
    const changed = Object.keys(changes).filter(
      (key) =>
        JSON.stringify(policy[key as keyof Policy]) !== JSON.stringify(updated[key as keyof Policy]),
    )
    const before = Object.fromEntries(changed.map((k) => [k, policy[k as keyof Policy]]))
    const after = Object.fromEntries(changed.map((k) => [k, updated[k as keyof Policy]]))
    Object.assign(policy, changes, { updated_at: new Date().toISOString() })
    if (changed.length) {
      addEvent(draft, 'policy.updated', {
        actor: draft.state.currentUser.email,
        agent_id: policy.agent_id,
        created_at: policy.updated_at,
        payload: { policy: policy.name, before, after },
      })
    }
    return policy
  })
}

/** Register an agent with backend-default limits. Returns the raw key, shown once. */
export function createAgent(name: string, description: string) {
  return mutate((draft) => {
    const clean = name.trim()
    if (!/^[a-z0-9][a-z0-9-]{1,48}$/.test(clean)) {
      throw new DemoError('Use 2 to 50 lowercase letters, numbers or dashes.')
    }
    if (draft.state.agents.some((a) => a.name === clean)) {
      throw new DemoError('An agent with this name already exists.')
    }
    const now = new Date().toISOString()
    const rawKey = newKey()
    const agent: Agent = {
      id: Math.max(0, ...draft.state.agents.map((a) => a.id)) + 1,
      name: clean,
      description: description.trim(),
      status: 'active',
      api_key_prefix: rawKey.slice(0, 8),
      created_at: now,
      last_used_at: null,
    }
    draft.state.agents.push(agent)
    // Same defaults as backend/gate/models.py Policy.
    draft.state.policies.push({
      id: Math.max(0, ...draft.state.policies.map((p) => p.id)) + 1,
      name: `${clean} policy`,
      agent_id: agent.id,
      currency: 'USD',
      per_transaction_cap: 100,
      approval_threshold: 50,
      daily_budget: 500,
      monthly_budget: 5000,
      allowed_merchants: [],
      blocked_merchants: [],
      updated_at: now,
    })
    const actor = draft.state.currentUser.email
    addEvent(draft, 'agent.created', { actor, agent_id: agent.id, created_at: now })
    addEvent(draft, 'agent.key_created', {
      actor,
      agent_id: agent.id,
      created_at: now,
      payload: { key_prefix: agent.api_key_prefix },
    })
    return { agent, rawKey }
  })
}

export function setAgentStatus(agentId: number, status: Agent['status']) {
  mutate((draft) => {
    const agent = findAgent(draft, agentId)
    if (agent.status === status) return
    agent.status = status
    addEvent(draft, status === 'suspended' ? 'agent.suspended' : 'agent.reactivated', {
      actor: draft.state.currentUser.email,
      agent_id: agent.id,
      created_at: new Date().toISOString(),
    })
  })
}

export function revokeKey(agentId: number) {
  mutate((draft) => {
    const agent = findAgent(draft, agentId)
    if (!agent.api_key_prefix) return
    addEvent(draft, 'agent.key_revoked', {
      actor: draft.state.currentUser.email,
      agent_id: agent.id,
      created_at: new Date().toISOString(),
      payload: { key_prefix: agent.api_key_prefix },
    })
    agent.api_key_prefix = ''
  })
}

/** Replace the agent's key. The old key stops working. Returns the raw key, shown once. */
export function rotateKey(agentId: number) {
  return mutate((draft) => {
    const agent = findAgent(draft, agentId)
    const now = new Date().toISOString()
    const actor = draft.state.currentUser.email
    if (agent.api_key_prefix) {
      addEvent(draft, 'agent.key_revoked', {
        actor,
        agent_id: agent.id,
        created_at: now,
        payload: { key_prefix: agent.api_key_prefix },
      })
    }
    const rawKey = newKey()
    agent.api_key_prefix = rawKey.slice(0, 8)
    addEvent(draft, 'agent.key_created', {
      actor,
      agent_id: agent.id,
      created_at: now,
      payload: { key_prefix: agent.api_key_prefix },
    })
    return rawKey
  })
}
