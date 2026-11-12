import { apiRequest } from './client'
import { pageQuery, type ListOptions, type Page, type UUID, type IsoDateTime } from './types'

export type MerchantMode = 'allowlist_only' | 'blocklist'
export type UntrustedSourceAction = 'needs_approval' | 'deny'
export type MerchantRuleKind = 'allow' | 'block'

export interface MerchantRule {
  id: UUID
  merchant_ref: string
  kind: MerchantRuleKind
  note: string
}

export interface Policy {
  id: UUID
  organization: UUID
  agent: UUID
  agent_name: string
  name: string
  version: number
  currency: string
  per_transaction_cap_minor: number
  daily_budget_minor: number
  weekly_budget_minor: number
  monthly_budget_minor: number
  approval_threshold_minor: number
  merchant_mode: MerchantMode
  velocity_max_count: number
  velocity_window_seconds: number
  merchant_window_cap_minor: number
  new_payee_cooldown_hours: number
  untrusted_source_action: UntrustedSourceAction
  injection_escalate_threshold: number
  classifier_required: boolean
  approval_ttl_minutes: number
  timezone: string
  merchant_rules: MerchantRule[]
  created_at: IsoDateTime
  updated_at: IsoDateTime
}

export interface MerchantRuleInput {
  merchant_ref: string
  kind: MerchantRuleKind
  note?: string
}

export interface PolicyCreateInput {
  agent: UUID
  currency?: string
  name?: string
  per_transaction_cap?: string
  daily_budget?: string
  weekly_budget?: string
  monthly_budget?: string
  approval_threshold?: string
  merchant_window_cap?: string
  merchant_mode?: MerchantMode
  velocity_max_count?: number
  velocity_window_seconds?: number
  new_payee_cooldown_hours?: number
  untrusted_source_action?: UntrustedSourceAction
  injection_escalate_threshold?: number
  classifier_required?: boolean
  approval_ttl_minutes?: number
  timezone?: string
  merchant_rules?: MerchantRuleInput[]
}

export type PolicyUpdateInput = Partial<Omit<PolicyCreateInput, 'agent'>> & {
  expected_version: number
}

export interface AddMerchantRuleInput extends MerchantRuleInput {
  expected_version: number
}

export interface PolicyListOptions extends ListOptions {
  agent?: UUID
}

export function listPolicies(
  options: PolicyListOptions = {},
): Promise<Page<Policy>> {
  const query = new URLSearchParams(pageQuery(options).slice(1))
  if (options.agent) query.set('agent', options.agent)
  return apiRequest<Page<Policy>>(`/v1/policies/?${query.toString()}`, {
    signal: options.signal,
  })
}

export function getPolicy(id: UUID, signal?: AbortSignal): Promise<Policy> {
  return apiRequest<Policy>(`/v1/policies/${encodeURIComponent(id)}/`, { signal })
}

export function createPolicy(
  input: PolicyCreateInput,
  signal?: AbortSignal,
): Promise<Policy> {
  return apiRequest<Policy>('/v1/policies/', { method: 'POST', body: input, signal })
}

export function updatePolicy(
  id: UUID,
  input: PolicyUpdateInput,
  signal?: AbortSignal,
): Promise<Policy> {
  return apiRequest<Policy>(`/v1/policies/${encodeURIComponent(id)}/`, {
    method: 'PATCH',
    body: input,
    signal,
  })
}

export function addMerchantRule(
  id: UUID,
  input: AddMerchantRuleInput,
  signal?: AbortSignal,
): Promise<Policy> {
  return apiRequest<Policy>(`/v1/policies/${encodeURIComponent(id)}/merchant-rules/`, {
    method: 'POST',
    body: input,
    signal,
  })
}

export function removeMerchantRule(
  id: UUID,
  ruleId: UUID,
  expectedVersion: number,
  signal?: AbortSignal,
): Promise<Policy> {
  return apiRequest<Policy>(
    `/v1/policies/${encodeURIComponent(id)}/merchant-rules/${encodeURIComponent(ruleId)}/`,
    {
      method: 'DELETE',
      headers: { 'If-Match': String(expectedVersion) },
      signal,
    },
  )
}
