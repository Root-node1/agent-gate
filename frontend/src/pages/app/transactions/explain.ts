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
      return `The request passed every rule in ${agent}'s demo policy. This is a local simulation; no payment request was sent.`
    case 'deny': {
      const hard = request.reasons.filter((r) => RULE_INFO[r.code]?.outcome !== 'needs_approval')
      const hardLabels = hard.map((r) => (RULE_INFO[r.code]?.label ?? r.code).toLowerCase())
      return `The demo policy blocked this request because it broke ${hard.length === 1 ? 'a hard rule' : `${hard.length} hard rules`}: ${joinWords(hardLabels)}. No PayPal call was made.`
    }
    case 'needs_approval':
      return `The demo held this request for a person to check because: ${joinWords(labels)}. No PayPal call was made.`
    case 'pending':
      return 'AgentGate has not decided yet.'
  }
}

/** Explain the simulated payment result without implying a PayPal API call. */
export function explainPayment(request: SpendRequest, approval?: Approval): string {
  switch (request.payment_status) {
    case 'completed':
      return 'Demo only: a successful PayPal response is simulated; no payment was made.'
    case 'processing':
      return 'Demo only: simulating a PayPal response; no request was sent to PayPal.'
    case 'failed':
      return 'Demo only: a PayPal rejection is simulated; no payment was attempted.'
    case 'awaiting_approval':
      return 'The demo is holding the request for approval. It has not called PayPal.'
    case 'not_sent':
      if (approval?.outcome === 'denied') return 'The demo recorded a denial; no PayPal call was made.'
      if (approval?.outcome === 'expired') return 'The demo request expired without a decision; no PayPal call was made.'
      return 'The demo policy blocked the request; no PayPal call was made.'
  }
}
