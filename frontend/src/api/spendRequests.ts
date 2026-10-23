// Mirrors backend/gate/serializers.py. Replace with generated types once
// openapi-typescript is set up.

export type Source = 'trusted' | 'untrusted' | 'unknown'
export type Decision = 'pending' | 'allow' | 'deny' | 'needs_approval'
export type ApprovalOutcome = 'pending' | 'approved' | 'denied'

export interface Reason {
  code: string
  message: string
}

export interface SpendRequestInput {
  amount: string
  currency: string
  merchant: string
  purpose: string
  source: Source
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
  reasons: Reason[]
  matched_rules: string[]
  paypal_reference: string
  created_at: string
  approval: ApprovalOutcome | null
}

/** Field errors from DRF validation (400), keyed by field name. */
export type FieldErrors = Partial<Record<keyof SpendRequestInput, string>>

export class ApiError extends Error {
  readonly status: number
  readonly fieldErrors: FieldErrors

  constructor(message: string, status: number, fieldErrors: FieldErrors = {}) {
    super(message)
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function isRequestId(value: string): boolean {
  return UUID_PATTERN.test(value)
}

async function agentFetch(agentKey: string, path: string, init: RequestInit = {}) {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${agentKey}`,
      },
    })
  } catch {
    throw new ApiError('Cannot reach the backend. Is it running on port 8000?', 0)
  }
  const body = await res.json().catch(() => ({}))

  if (res.status === 401 || res.status === 403) {
    throw new ApiError('Agent key is wrong or the agent is suspended.', res.status)
  }
  return { status: res.status, body }
}

export async function submitSpendRequest(
  agentKey: string,
  input: SpendRequestInput,
): Promise<SpendRequest> {
  const { status, body } = await agentFetch(agentKey, '/v1/spend-requests/', {
    method: 'POST',
    body: JSON.stringify(input),
  })

  // 201 is returned for every decision; the caller must read `decision`.
  if (status === 201) return body as SpendRequest

  if (status === 400) {
    const fieldErrors: FieldErrors = {}
    for (const [field, messages] of Object.entries(body)) {
      fieldErrors[field as keyof SpendRequestInput] = Array.isArray(messages)
        ? messages.join(' ')
        : String(messages)
    }
    throw new ApiError('Check the highlighted fields.', 400, fieldErrors)
  }

  if (status === 409) {
    throw new ApiError('This agent has no spending policy yet. Set one up first.', 409)
  }

  throw new ApiError(body.detail ?? `Unexpected error (${status}).`, status)
}

export async function getSpendRequest(agentKey: string, id: string): Promise<SpendRequest> {
  const { status, body } = await agentFetch(agentKey, `/v1/spend-requests/${id}/`)

  if (status === 200) return body as SpendRequest

  // The backend only shows an agent its own requests, so a 404 can also mean
  // the request belongs to a different agent.
  if (status === 404) {
    throw new ApiError('No request with this ID for this agent. Check the ID and the agent key.', 404)
  }

  throw new ApiError(body.detail ?? `Unexpected error (${status}).`, status)
}
