import { RULE_INFO } from '../../../demo/rules'
import type { Approval, SpendRequest } from '../../../demo/types'

function joinWords(items: string[]): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`
}

/** One or two plain-English sentences on why AgentGate decided what it did. */
export function explainDecision(request: SpendRequest, agent: string): string {
  const labels = request.reasons.map((r) => (RULE_INFO[r.code]?.label ?? r.code).toLowerCase())
  switch (request.decision) {
    case 'allow':
      return `The request passed every rule in ${agent}'s policy, so AgentGate sent it to PayPal without asking anyone.`
    case 'deny': {
      const hard = request.reasons.filter((r) => RULE_INFO[r.code]?.outcome !== 'needs_approval')
      const hardLabels = hard.map((r) => (RULE_INFO[r.code]?.label ?? r.code).toLowerCase())
      return `AgentGate blocked this request because it broke ${hard.length === 1 ? 'a hard rule' : `${hard.length} hard rules`}: ${joinWords(hardLabels)}. Nothing was sent to PayPal.`
    }
    case 'needs_approval':
      return `No hard rule was broken, but AgentGate held the payment for a person to check because: ${joinWords(labels)}.`
    case 'pending':
      return 'AgentGate has not decided yet.'
  }
}

/** What happened (or will happen) at PayPal, in plain English. */
export function explainPayment(request: SpendRequest, approval?: Approval): string {
  switch (request.payment_status) {
    case 'completed':
      return 'PayPal confirmed the payment.'
    case 'processing':
      return 'Sent to PayPal. Waiting for PayPal to confirm.'
    case 'failed':
      return 'AgentGate allowed it, but PayPal rejected the payment, so no money moved.'
    case 'awaiting_approval':
      return 'Nothing is sent to PayPal until a person approves it.'
    case 'not_sent':
      if (approval?.outcome === 'denied') return 'A person denied it, so nothing was sent to PayPal.'
      if (approval?.outcome === 'expired') return 'Nobody decided in time, so nothing was sent to PayPal.'
      return 'Blocked by policy, so nothing was sent to PayPal.'
  }
}
