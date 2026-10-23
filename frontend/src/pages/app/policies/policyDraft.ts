import type { Limits } from '../../../demo/rules'
import type { Policy } from '../../../demo/types'

export const MONEY_FIELDS = ['daily_budget', 'monthly_budget', 'per_transaction_cap', 'approval_threshold'] as const
export type MoneyField = (typeof MONEY_FIELDS)[number]

export const CURRENCIES = [
  { code: 'USD', label: 'USD – US dollar' },
  { code: 'EUR', label: 'EUR – Euro' },
  { code: 'GBP', label: 'GBP – British pound' },
  { code: 'CAD', label: 'CAD – Canadian dollar' },
  { code: 'AUD', label: 'AUD – Australian dollar' },
  { code: 'JPY', label: 'JPY – Japanese yen' },
  { code: 'CHF', label: 'CHF – Swiss franc' },
  { code: 'KES', label: 'KES – Kenyan shilling' },
]

/** Form state: money stays as typed text until saved. */
export interface PolicyDraft {
  name: string
  currency: string
  daily_budget: string
  monthly_budget: string
  per_transaction_cap: string
  approval_threshold: string
  allowed_merchants: string[]
  blocked_merchants: string[]
}

export type PolicyValues = Omit<Policy, 'id' | 'agent_id' | 'updated_at'>

export function draftFromPolicy(p: Policy): PolicyDraft {
  return {
    name: p.name,
    currency: p.currency,
    daily_budget: String(p.daily_budget),
    monthly_budget: String(p.monthly_budget),
    per_transaction_cap: String(p.per_transaction_cap),
    approval_threshold: String(p.approval_threshold),
    allowed_merchants: [...p.allowed_merchants],
    blocked_merchants: [...p.blocked_merchants],
  }
}

export function parseMoney(value: string): number {
  const clean = value.replace(/[,\s]/g, '')
  if (!/^\d*\.?\d+$|^\d+\.$/.test(clean)) return NaN
  return Math.round(Number(clean) * 100) / 100
}

export function valuesFromDraft(d: PolicyDraft): PolicyValues {
  return {
    name: d.name.trim(),
    currency: d.currency,
    daily_budget: parseMoney(d.daily_budget),
    monthly_budget: parseMoney(d.monthly_budget),
    per_transaction_cap: parseMoney(d.per_transaction_cap),
    approval_threshold: parseMoney(d.approval_threshold),
    allowed_merchants: d.allowed_merchants,
    blocked_merchants: d.blocked_merchants,
  }
}

export function isDirty(d: PolicyDraft, p: Policy): boolean {
  const v = valuesFromDraft(d)
  return (
    v.name !== p.name ||
    v.currency !== p.currency ||
    MONEY_FIELDS.some((f) => v[f] !== p[f]) ||
    v.allowed_merchants.join('\n') !== p.allowed_merchants.join('\n') ||
    v.blocked_merchants.join('\n') !== p.blocked_merchants.join('\n')
  )
}

export function limitsFromValues(v: PolicyValues): Limits {
  return {
    currency: v.currency,
    per_transaction_cap: v.per_transaction_cap,
    approval_threshold: v.approval_threshold,
    daily_budget: v.daily_budget,
    monthly_budget: v.monthly_budget,
    allowed_merchants: v.allowed_merchants,
    blocked_merchants: v.blocked_merchants,
  }
}

/** "$" for USD, "€" for EUR, falls back to the code. */
export function currencySymbol(code: string): string {
  try {
    const parts = new Intl.NumberFormat('en-US', { style: 'currency', currency: code }).formatToParts(0)
    return parts.find((p) => p.type === 'currency')?.value ?? code
  } catch {
    return code
  }
}

export type MerchantList = 'allowed_merchants' | 'blocked_merchants'

export const LIST_NAMES: Record<MerchantList, string> = {
  allowed_merchants: 'allow list',
  blocked_merchants: 'block list',
}

export function merchantError(value: string, list: MerchantList, draft: PolicyDraft): string | null {
  if (!value) return 'Enter a merchant domain, e.g. github.com.'
  if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/.test(value)) {
    return 'Use a domain like github.com.'
  }
  if (draft[list].includes(value)) return `${value} is already on the ${LIST_NAMES[list]}.`
  const other: MerchantList = list === 'allowed_merchants' ? 'blocked_merchants' : 'allowed_merchants'
  if (draft[other].includes(value)) {
    return `${value} is on the ${LIST_NAMES[other]}. Remove it there first.`
  }
  return null
}
