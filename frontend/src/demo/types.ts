// Demo data model. Mirrors backend/gate/models.py, plus the pieces the
// dashboard needs that the backend does not have yet (marked "planned").

import type { Decision, Reason, Source } from '../api/spendRequests'

export type { Decision, Reason, Source }

export type AgentStatus = 'active' | 'suspended'

export interface Agent {
  id: number
  name: string
  description: string
  status: AgentStatus
  /** First 8 characters of the current key, e.g. "agk_Xy12". Empty once revoked. */
  api_key_prefix: string
  created_at: string
  last_used_at: string | null
}

export interface Policy {
  id: number
  /** Planned: the backend policy has no name; we show one for readability. */
  name: string
  /** One policy per agent in the backend (OneToOne). */
  agent_id: number
  currency: string
  per_transaction_cap: number
  approval_threshold: number
  daily_budget: number
  monthly_budget: number
  allowed_merchants: string[]
  blocked_merchants: string[]
  updated_at: string
}

/** Planned: the backend only stores paypal_reference so far. */
export type PaymentStatus = 'not_sent' | 'awaiting_approval' | 'processing' | 'completed' | 'failed'

export interface SpendRequest {
  id: string
  agent_id: number
  amount: number
  currency: string
  merchant: string
  purpose: string
  source: Source
  risk_score: number
  decision: Decision
  reasons: Reason[]
  matched_rules: string[]
  payment_status: PaymentStatus
  paypal_reference: string
  created_at: string
}

/** "expired" is planned: the backend has pending, approved and denied. */
export type ApprovalOutcome = 'pending' | 'approved' | 'denied' | 'expired'

export interface Approval {
  id: number
  spend_request_id: string
  outcome: ApprovalOutcome
  approver: string | null
  note: string
  created_at: string
  /** Pending approvals expire after this time. */
  expires_at: string
  decided_at: string | null
}

export type AuditEventType =
  | 'spend_request.received'
  | 'spend_request.decided'
  | 'approval.requested'
  | 'approval.approved'
  | 'approval.denied'
  | 'approval.expired'
  | 'payment.processing'
  | 'payment.completed'
  | 'payment.failed'
  | 'agent.created'
  | 'agent.suspended'
  | 'agent.reactivated'
  | 'agent.key_created'
  | 'agent.key_revoked'
  | 'policy.updated'

export interface AuditEvent {
  id: number
  event_type: AuditEventType
  created_at: string
  /** Who did it: an agent name, "AgentGate", "PayPal", or a person's email. */
  actor: string
  agent_id: number | null
  spend_request_id: string | null
  payload: Record<string, unknown>
}

export type Role = 'admin' | 'approver' | 'viewer'

export interface TeamMember {
  id: number
  name: string
  email: string
  role: Role
}

export interface DemoState {
  agents: Agent[]
  policies: Policy[]
  requests: SpendRequest[]
  approvals: Approval[]
  events: AuditEvent[]
  team: TeamMember[]
  /** The signed-in demo user. */
  currentUser: TeamMember
}
