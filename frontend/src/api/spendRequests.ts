import { ApiError as HttpApiError, apiRequest } from './client'
import type { ListOptions, Page, UUID } from './types'

export type Source =
  | 'trusted'
  | 'untrusted'
  | 'web_page'
  | 'email'
  | 'invoice'
  | 'tool_output'
  | 'unknown'
export type Decision = 'allow' | 'deny' | 'needs_approval'
export type ApprovalOutcome = 'pending' | 'approved' | 'denied' | 'expired'
export type SpendRequestStatus =
  | 'pending_approval'
  | 'denied'
  | 'approved'
  | 'executing'
  | 'succeeded'
  | 'failed'
  | 'execution_blocked'
  | 'expired'
  | 'rejected'
  | 'reversed'

export interface Reason {
  code: string
  message: string
}

export interface SpendRequestInput {
  amount: string
  currency: string
  merchant: string
  purpose: string
  source_ref?: string
  evidence_excerpt?: string
  destination_type?: string
  destination_value?: string
}

export interface SpendRequest {
  id: string
  amount: string
  currency: string
  merchant: string
  purpose: string
  source: Source
  risk_score: number
  decision: Decision
  status: SpendRequestStatus
  reasons: Reason[]
  matched_rules: string[]
  paypal_reference: string | null
  created_at: string
  approval: ApprovalOutcome | null
}

/** Field errors from DRF validation (400), keyed by field name. */
export type FieldErrors = Partial<Record<keyof SpendRequestInput | 'non_field', string>>

export class ApiError extends Error {
  readonly status: number
  readonly fieldErrors: FieldErrors

  constructor(message: string, status: number, fieldErrors: FieldErrors = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

export interface SpendRequestListOptions extends ListOptions {
  status?: SpendRequestStatus
  decision?: Decision
  agent?: UUID
  created_after?: string
  created_before?: string
  ordering?: string
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function isRequestId(value: string): boolean {
  return UUID_PATTERN.test(value)
}

function mapRequestError(error: unknown, agentKey = false): ApiError {
  if (error instanceof Error && error.name === 'AbortError') throw error
  if (!(error instanceof HttpApiError)) {
    return new ApiError(
      error instanceof Error ? error.message : 'The request could not be completed.',
      0,
    )
  }
  if (agentKey && (error.status === 401 || error.status === 403)) {
    return new ApiError('Agent key is invalid or the agent is suspended.', error.status)
  }
  const fieldErrors: FieldErrors = {}
  for (const [field, messages] of Object.entries(error.fieldErrors)) {
    fieldErrors[field as keyof FieldErrors] = messages.join(' ')
  }
  return new ApiError(error.message, error.status, fieldErrors)
}

export async function submitSpendRequest(
  agentKey: string,
  input: SpendRequestInput,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<SpendRequest> {
  try {
    return await apiRequest<SpendRequest>('/v1/spend-requests/', {
      method: 'POST',
      body: input,
      headers: { 'Idempotency-Key': idempotencyKey },
      auth: 'agent',
      agentKey,
      signal,
    })
  } catch (error) {
    const mapped = mapRequestError(error, true)
    if (mapped.status === 409 && error instanceof HttpApiError) {
      if (error.code === 'policy_missing') {
        throw new ApiError('This agent has no spending policy yet. Set one up first.', 409)
      }
      if (error.code === 'idempotency_conflict') {
        throw new ApiError('This request key was already used for different request data.', 409)
      }
    }
    if (mapped.status === 400) {
      throw new ApiError('Check the highlighted fields.', 400, mapped.fieldErrors)
    }
    throw mapped
  }
}

export async function getSpendRequest(
  agentKey: string,
  id: string,
  signal?: AbortSignal,
): Promise<SpendRequest> {
  try {
    return await apiRequest<SpendRequest>(
      `/v1/spend-requests/${encodeURIComponent(id)}/`,
      { auth: 'agent', agentKey, signal },
    )
  } catch (error) {
    const mapped = mapRequestError(error, true)
    if (mapped.status === 404) {
      throw new ApiError(
        'No request with this ID for this agent. Check the ID and the agent key.',
        404,
      )
    }
    throw mapped
  }
}

export function listSpendRequests(
  options: SpendRequestListOptions = {},
): Promise<Page<SpendRequest>> {
  const query = new URLSearchParams()
  for (const key of [
    'limit',
    'offset',
    'status',
    'decision',
    'agent',
    'created_after',
    'created_before',
    'ordering',
  ] as const) {
    const value = options[key]
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const suffix = query.toString()
  return apiRequest<Page<SpendRequest>>(`/v1/spend-requests/${suffix ? `?${suffix}` : ''}`, {
    signal: options.signal,
  })
}
