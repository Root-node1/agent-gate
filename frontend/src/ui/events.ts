import { agentName, requestById } from '../demo/selectors'
import type { AuditEvent, DemoState } from '../demo/types'
import { formatMoney } from './format'
import { DECISION } from './labels'

const FIELD_NAMES: Record<string, string> = {
  name: 'name',
  currency: 'currency',
  per_transaction_cap: 'per-transaction cap',
  approval_threshold: 'approval threshold',
  daily_budget: 'daily budget',
  monthly_budget: 'monthly budget',
  allowed_merchants: 'allow list',
  blocked_merchants: 'block list',
}

/** One plain-English sentence explaining an audit event. */
export function describeEvent(s: DemoState, e: AuditEvent): string {
  const request = requestById(s, e.spend_request_id)
  const agent = agentName(s, e.agent_id)
  const money = request ? formatMoney(request.amount, request.currency) : ''
  const p = e.payload as Record<string, unknown>

  switch (e.event_type) {
    case 'spend_request.received':
      return `${agent} asked to pay ${money} to ${request?.merchant ?? p.merchant}.`
    case 'spend_request.decided': {
      const decision = request?.decision ?? (p.decision as keyof typeof DECISION)
      const rules = (p.rules as string[] | undefined) ?? []
      return `${DECISION[decision].label}${rules.length ? `: ${rules.join(', ')}` : ': passed every rule'}.`
    }
    case 'approval.requested':
      return 'Held for a person to approve or deny.'
    case 'approval.approved':
      return `${e.actor} approved the payment${p.note ? `: “${p.note}”` : '.'}`
    case 'approval.denied':
      return `${e.actor} denied the payment${p.note ? `: “${p.note}”` : '.'}`
    case 'approval.expired':
      return 'Nobody decided in time, so the request expired and nothing was paid.'
    case 'payment.processing':
      return `Sent ${money} to PayPal.`
    case 'payment.completed':
      return `PayPal confirmed the payment (${p.paypal_reference}).`
    case 'payment.failed':
      return `PayPal rejected the payment: ${p.error}`
    case 'agent.created':
      return `${e.actor} registered ${agent}.`
    case 'agent.suspended':
      return `${e.actor} suspended ${agent}${p.note ? `: ${p.note}` : '.'}`
    case 'agent.reactivated':
      return `${e.actor} reactivated ${agent}.`
    case 'agent.key_created':
      return `New API key ${p.key_prefix}… created for ${agent}.`
    case 'agent.key_revoked':
      return `API key ${p.key_prefix}… revoked for ${agent}. It no longer works.`
    case 'policy.updated': {
      const after = (p.after ?? {}) as Record<string, unknown>
      const fields = Object.keys(after).map((k) => FIELD_NAMES[k] ?? k)
      return `${e.actor} changed ${fields.join(', ') || 'nothing'} on ${p.policy}.`
    }
  }
}
