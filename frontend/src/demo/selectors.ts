// Read-only helpers over DemoState. Pages derive everything they show from these.

import { countedSpend, spentWindows } from './store'
import type { Agent, Approval, AuditEvent, DemoState, Policy, SpendRequest } from './types'

export function agentById(s: DemoState, id: number | null): Agent | undefined {
  return id === null ? undefined : s.agents.find((a) => a.id === id)
}

export function agentName(s: DemoState, id: number | null): string {
  return agentById(s, id)?.name ?? '—'
}

export function policyForAgent(s: DemoState, agentId: number): Policy | undefined {
  return s.policies.find((p) => p.agent_id === agentId)
}

export function requestById(s: DemoState, id: string | null): SpendRequest | undefined {
  return id === null ? undefined : s.requests.find((r) => r.id === id)
}

export function approvalForRequest(s: DemoState, requestId: string): Approval | undefined {
  return s.approvals.find((a) => a.spend_request_id === requestId)
}

/** Events for one request, oldest first: a timeline. */
export function timelineForRequest(s: DemoState, requestId: string): AuditEvent[] {
  return s.events.filter((e) => e.spend_request_id === requestId).reverse()
}

export interface BudgetUsage {
  currency: string
  today: number
  dailyBudget: number
  month: number
  monthlyBudget: number
}

export function budgetUsage(s: DemoState, agentId: number, now = new Date()): BudgetUsage | undefined {
  const policy = policyForAgent(s, agentId)
  if (!policy) return undefined
  const spent = spentWindows(s, agentId, policy.currency, now)
  return {
    currency: policy.currency,
    today: spent.today,
    dailyBudget: policy.daily_budget,
    month: spent.this_month,
    monthlyBudget: policy.monthly_budget,
  }
}

/** Budget usage summed over all active agents (all seeded policies use USD). */
export function workspaceBudget(s: DemoState, now = new Date()): BudgetUsage {
  const total: BudgetUsage = { currency: 'USD', today: 0, dailyBudget: 0, month: 0, monthlyBudget: 0 }
  for (const agent of s.agents) {
    if (agent.status !== 'active') continue
    const usage = budgetUsage(s, agent.id, now)
    if (!usage || usage.currency !== total.currency) continue
    total.today += usage.today
    total.dailyBudget += usage.dailyBudget
    total.month += usage.month
    total.monthlyBudget += usage.monthlyBudget
  }
  return total
}

export function decisionTotals(requests: SpendRequest[]) {
  return {
    total: requests.length,
    allow: requests.filter((r) => r.decision === 'allow').length,
    deny: requests.filter((r) => r.decision === 'deny').length,
    needs_approval: requests.filter((r) => r.decision === 'needs_approval').length,
  }
}

/** Pending past its deadline counts as expired, matching what decideApproval enforces. */
export function effectiveOutcome(a: Approval, now = Date.now()): Approval['outcome'] {
  return a.outcome === 'pending' && new Date(a.expires_at).getTime() <= now ? 'expired' : a.outcome
}

export function pendingApprovals(s: DemoState, now = Date.now()): Approval[] {
  return s.approvals
    .filter((a) => effectiveOutcome(a, now) === 'pending')
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
}

export interface DayCount {
  /** Local date, YYYY-MM-DD. */
  date: string
  allow: number
  deny: number
  needs_approval: number
}

function localDateKey(d: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Decisions per day for the last `days` days, oldest first, including empty days. */
export function decisionsByDay(s: DemoState, days = 14, now = new Date()): DayCount[] {
  const result: DayCount[] = []
  const index = new Map<string, DayCount>()
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i)
    const row = { date: localDateKey(d), allow: 0, deny: 0, needs_approval: 0 }
    result.push(row)
    index.set(row.date, row)
  }
  for (const r of s.requests) {
    const row = index.get(localDateKey(new Date(r.created_at)))
    if (row && r.decision !== 'pending') row[r.decision]++
  }
  return result
}

export interface RiskIndicator {
  level: 'high' | 'medium'
  label: string
}

const URGENT_WORDS = /\b(urgent|immediately|overdue|locked|verify|verification|suspend|shutdown|ignore)\b/i

/**
 * Demo-only risk hints for reviewers. The backend's risk_score stays 0 until the
 * injection classifier lands, so these are simple, explainable heuristics.
 */
export function riskIndicators(s: DemoState, request: SpendRequest): RiskIndicator[] {
  const indicators: RiskIndicator[] = []
  if (request.source === 'untrusted') {
    indicators.push({ level: 'high', label: 'Instruction came from a web page, email or invoice' })
  } else if (request.source === 'unknown') {
    indicators.push({ level: 'medium', label: 'Agent did not say where the instruction came from' })
  }
  if (URGENT_WORDS.test(request.purpose)) {
    indicators.push({ level: 'high', label: 'Pressure words in the purpose, common in phishing' })
  }
  const earlier = s.requests.filter(
    (r) => r.agent_id === request.agent_id && r.created_at < request.created_at,
  )
  if (!earlier.some((r) => r.merchant === request.merchant)) {
    indicators.push({ level: 'medium', label: 'First payment to this merchant' })
  }
  const paid = earlier.filter((r) => r.decision === 'allow').map((r) => r.amount)
  if (paid.length >= 3) {
    const average = paid.reduce((a, b) => a + b, 0) / paid.length
    if (request.amount > average * 3) {
      indicators.push({
        level: 'medium',
        label: `About ${Math.round(request.amount / average)}× this agent's usual payment`,
      })
    }
  }
  return indicators
}

export { countedSpend }
