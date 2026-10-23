import type { AgentStatus, ApprovalOutcome, Decision, PaymentStatus } from '../demo/types'
import { StatusBadge } from './Badge'
import { AGENT_STATUS, APPROVAL, DECISION, PAYMENT } from './labels'

/** Policy decision from AgentGate: solid pill. */
export function DecisionStatus({ decision }: { decision: Decision }) {
  return <StatusBadge status={DECISION[decision]} />
}

/** Payment execution at PayPal: outline pill, so "Allowed" and "Paid" never look the same. */
export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  return <StatusBadge status={PAYMENT[status]} variant="outline" title={PAYMENT[status].summary} />
}

export function ApprovalStatus({ outcome }: { outcome: ApprovalOutcome }) {
  return <StatusBadge status={APPROVAL[outcome]} />
}

export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  return <StatusBadge status={AGENT_STATUS[status]} />
}
