// TypeScript copy of backend/gate/rules.py so the demo makes the same decisions
// as the real API. Keep codes, messages and precedence in sync with the backend.

import type { Decision, Reason, Source } from './types'

export interface Limits {
  currency: string
  per_transaction_cap: number
  approval_threshold: number
  daily_budget: number
  monthly_budget: number
  allowed_merchants: string[]
  blocked_merchants: string[]
}

export interface SpendInput {
  amount: number
  currency: string
  merchant: string
  source: Source
}

export interface Spent {
  today: number
  this_month: number
}

export interface RuleResult extends Reason {
  outcome: 'deny' | 'needs_approval'
}

export interface Evaluation {
  decision: Exclude<Decision, 'pending'>
  reasons: RuleResult[]
}

/** Lowercase and strip scheme, path and a leading www so URLs match plain domains. */
export function normalizeMerchant(value: string): string {
  let merchant = value.trim().toLowerCase()
  merchant = merchant.split('://').at(-1) ?? merchant
  merchant = merchant.split('/')[0]
  if (merchant.startsWith('www.')) merchant = merchant.slice(4)
  return merchant
}

const fmt = (n: number) => n.toFixed(2)

export function evaluate(spend: SpendInput, limits: Limits, spent: Spent): Evaluation {
  const reasons: RuleResult[] = []
  const merchant = normalizeMerchant(spend.merchant)
  const blocked = new Set(limits.blocked_merchants.map(normalizeMerchant))
  const allowed = new Set(limits.allowed_merchants.map(normalizeMerchant))
  const currency = limits.currency
  const deny = (code: string, message: string) => reasons.push({ code, message, outcome: 'deny' })
  const needsApproval = (code: string, message: string) =>
    reasons.push({ code, message, outcome: 'needs_approval' })

  // Hard rules: any of these denies the request.
  if (spend.amount <= 0) deny('INVALID_AMOUNT', 'Amount must be greater than zero.')
  if (spend.currency.toUpperCase() !== currency.toUpperCase()) {
    deny('CURRENCY_MISMATCH', `Request is in ${spend.currency}, policy is in ${currency}.`)
  }
  if (blocked.has(merchant)) deny('MERCHANT_BLOCKED', `Merchant ${merchant} is on the block list.`)
  if (allowed.size > 0 && !allowed.has(merchant)) {
    deny('MERCHANT_NOT_ALLOWED', `Merchant ${merchant} is not on the allow list.`)
  }
  if (spend.amount > limits.per_transaction_cap) {
    deny(
      'OVER_TRANSACTION_CAP',
      `${fmt(spend.amount)} ${currency} exceeds the per-transaction cap of ${fmt(limits.per_transaction_cap)}.`,
    )
  }
  if (spent.today + spend.amount > limits.daily_budget) {
    deny(
      'OVER_DAILY_BUDGET',
      `Would bring today's spend to ${fmt(spent.today + spend.amount)} ${currency}, ` +
        `over the daily budget of ${fmt(limits.daily_budget)}.`,
    )
  }
  if (spent.this_month + spend.amount > limits.monthly_budget) {
    deny(
      'OVER_MONTHLY_BUDGET',
      `Would bring this month's spend to ${fmt(spent.this_month + spend.amount)} ${currency}, ` +
        `over the monthly budget of ${fmt(limits.monthly_budget)}.`,
    )
  }

  // Approval rules: a human must decide. Fail closed on anything not trusted.
  if (spend.source === 'untrusted') {
    needsApproval(
      'UNTRUSTED_SOURCE',
      'The payment instruction came from untrusted content (web page, email or invoice).',
    )
  } else if (spend.source !== 'trusted') {
    needsApproval('UNKNOWN_SOURCE', 'The origin of the payment instruction is unknown.')
  }
  if (spend.amount > limits.approval_threshold) {
    needsApproval(
      'OVER_APPROVAL_THRESHOLD',
      `${fmt(spend.amount)} ${currency} is above the approval threshold of ${fmt(limits.approval_threshold)}.`,
    )
  }

  const decision = reasons.some((r) => r.outcome === 'deny')
    ? 'deny'
    : reasons.length > 0
      ? 'needs_approval'
      : 'allow'
  return { decision, reasons }
}

/** Every rule the engine can trigger, for legends and the policy preview. */
export const RULE_INFO: Record<string, { outcome: 'deny' | 'needs_approval'; label: string }> = {
  INVALID_AMOUNT: { outcome: 'deny', label: 'Amount is zero or negative' },
  CURRENCY_MISMATCH: { outcome: 'deny', label: 'Currency differs from the policy' },
  MERCHANT_BLOCKED: { outcome: 'deny', label: 'Merchant is on the block list' },
  MERCHANT_NOT_ALLOWED: { outcome: 'deny', label: 'Merchant is not on the allow list' },
  OVER_TRANSACTION_CAP: { outcome: 'deny', label: 'Above the per-transaction cap' },
  OVER_DAILY_BUDGET: { outcome: 'deny', label: 'Over the daily budget' },
  OVER_MONTHLY_BUDGET: { outcome: 'deny', label: 'Over the monthly budget' },
  UNTRUSTED_SOURCE: { outcome: 'needs_approval', label: 'Instruction came from untrusted content' },
  UNKNOWN_SOURCE: { outcome: 'needs_approval', label: 'Instruction source is unknown' },
  OVER_APPROVAL_THRESHOLD: { outcome: 'needs_approval', label: 'Above the approval threshold' },
}
