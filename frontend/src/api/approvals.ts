import { apiRequest } from './client'
import { pageQuery, type ListOptions, type Page, type UUID, type IsoDateTime } from './types'

export type ApprovalOutcome = 'pending' | 'approved' | 'denied' | 'expired'
export type SpendDecision = 'allow' | 'deny' | 'needs_approval'
export type SpendStatus =
  | 'pending_approval'
  | 'denied'
  | 'approved'
  | 'executing'
  | 'succeeded'
  | 'failed'
  | 'execution_blocked'
  | 'rejected'
  | 'expired'
  | 'reversed'

export interface Approval {
  id: UUID
  organization: UUID
  spend_request: UUID
  agent: UUID
  agent_name: string
  amount: string
  currency: string
  merchant: string
  purpose: string
  source: string
  decision: SpendDecision
  status: SpendStatus
  matched_rules: string[]
  reasons: Array<{ code: string; message: string }>
  outcome: ApprovalOutcome
  approver: UUID | null
  note: string
  requested_at: IsoDateTime
  expires_at: IsoDateTime
  decided_at: IsoDateTime | null
}

export type ApprovalListOutcome = ApprovalOutcome | 'all'
export interface ApprovalListOptions extends ListOptions {
  outcome?: ApprovalListOutcome
}

export interface ApprovalDecisionInput {
  note?: string
}

export function listApprovals(
  options: ApprovalListOptions = {},
): Promise<Page<Approval>> {
  const query = new URLSearchParams(pageQuery(options).slice(1))
  if (options.outcome) query.set('outcome', options.outcome)
  return apiRequest<Page<Approval>>(`/v1/approvals/?${query.toString()}`, {
    signal: options.signal,
  })
}

export function getApproval(id: UUID, signal?: AbortSignal): Promise<Approval> {
  return apiRequest<Approval>(`/v1/approvals/${encodeURIComponent(id)}/`, { signal })
}

export function approveRequest(
  id: UUID,
  input: ApprovalDecisionInput = {},
  signal?: AbortSignal,
): Promise<Approval> {
  return apiRequest<Approval>(`/v1/approvals/${encodeURIComponent(id)}/approve/`, {
    method: 'POST',
    body: input,
    signal,
  })
}

export function denyRequest(
  id: UUID,
  input: ApprovalDecisionInput = {},
  signal?: AbortSignal,
): Promise<Approval> {
  return apiRequest<Approval>(`/v1/approvals/${encodeURIComponent(id)}/deny/`, {
    method: 'POST',
    body: input,
    signal,
  })
}
