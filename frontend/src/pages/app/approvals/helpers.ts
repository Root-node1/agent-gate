// Pure helpers for the approval queue and approval detail screens.

import { RULE_INFO } from '../../../demo/rules'
import { policyForAgent, riskIndicators, type RiskIndicator } from '../../../demo/selectors'
import type { Approval, ApprovalOutcome, DemoState, SpendRequest } from '../../../demo/types'
import { formatMoney } from '../../../ui/format'

export const TABS: { id: ApprovalOutcome; label: string }[] = [
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'denied', label: 'Denied' },
  { id: 'expired', label: 'Expired' },
]

export function isTab(value: string | null): value is ApprovalOutcome {
  return TABS.some((t) => t.id === value)
}

/**
 * The store only expires approvals when it is seeded, so a pending approval
 * can pass its deadline while the page is open. Treat it as expired then,
 * which is also what decideApproval enforces.
 */
export function effectiveOutcome(approval: Approval, now: number): ApprovalOutcome {
  if (approval.outcome === 'pending' && new Date(approval.expires_at).getTime() <= now) return 'expired'
  return approval.outcome
}

/** Short labels for the rules that sent this request to a person. */
export function escalationLabels(request: SpendRequest): string[] {
  return request.reasons
    .filter((r) => RULE_INFO[r.code]?.outcome === 'needs_approval')
    .map((r) => RULE_INFO[r.code]?.label ?? r.message)
}

export function highRisk(indicators: RiskIndicator[]): boolean {
  return indicators.some((i) => i.level === 'high')
}

/** "Expires in 3 h 20 min", "Expires in 12 min". */
export function expiresIn(expiresAt: string, now: number): { text: string; urgent: boolean } {
  const minutes = Math.max(0, Math.ceil((new Date(expiresAt).getTime() - now) / 60_000))
  const urgent = minutes < 60
  if (minutes < 60) return { text: `Expires in ${minutes} min`, urgent }
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return { text: `Expires in ${hours} h${rest ? ` ${rest} min` : ''}`, urgent }
}

/** A team member's name for an email, "you" for the signed-in user. */
export function personName(s: DemoState, email: string | null): string {
  if (!email) return 'Nobody'
  if (email === s.currentUser.email) return `You (${s.currentUser.name})`
  return s.team.find((m) => m.email === email)?.name ?? email
}

/**
 * Plain-English sentences explaining why a person has to decide. Written for
 * the reviewer, so they say what the risk is, not which rule code fired.
 */
export function whySentences(s: DemoState, request: SpendRequest): string[] {
  const policy = policyForAgent(s, request.agent_id)
  const money = (n: number) => formatMoney(n, request.currency)
  const sentences: string[] = []
  for (const reason of request.reasons) {
    switch (reason.code) {
      case 'UNTRUSTED_SOURCE':
        sentences.push(
          'The agent got this payment instruction from a web page, email or invoice. ' +
            'Content like that can trick an agent into paying someone it should not.',
        )
        break
      case 'UNKNOWN_SOURCE':
        sentences.push('The agent did not say where the instruction came from, so AgentGate cannot vouch for it.')
        break
      case 'OVER_APPROVAL_THRESHOLD':
        sentences.push(
          policy
            ? `${money(request.amount)} is above the ${money(policy.approval_threshold)} limit this agent may spend without a person.`
            : `${money(request.amount)} is above this agent's approval limit.`,
        )
        break
      default:
        sentences.push(reason.message)
    }
  }
  if (sentences.length === 0) sentences.push('A policy rule asked for a person to check this payment.')
  return sentences
}

/** The one thing a reviewer should weigh most, for the confirmation dialog. */
export function mainRisk(s: DemoState, request: SpendRequest): { text: string; high: boolean } {
  const indicators = riskIndicators(s, request)
  const high = indicators.find((i) => i.level === 'high')
  if (high) return { text: high.label, high: true }
  const label = escalationLabels(request)[0] ?? indicators[0]?.label
  return { text: label ?? 'No risk signals found', high: false }
}
