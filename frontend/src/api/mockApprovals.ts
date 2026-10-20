import type { Approval } from './approvals'
import type { Reason, SpendRequest } from './spendRequests'

// Sample data for the approval queue until the backend endpoints exist.
// Reasons use the real rule codes and messages from backend/gate/rules.py.

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString()

const UNTRUSTED: Reason = {
  code: 'UNTRUSTED_SOURCE',
  message: 'The payment instruction came from untrusted content (web page, email or invoice).',
}
const UNKNOWN: Reason = {
  code: 'UNKNOWN_SOURCE',
  message: 'The origin of the payment instruction is unknown.',
}
const overThreshold = (amount: string): Reason => ({
  code: 'OVER_APPROVAL_THRESHOLD',
  message: `${amount} USD is above the approval threshold of 50.00.`,
})

function spendRequest(
  id: string,
  fields: Pick<SpendRequest, 'amount' | 'merchant' | 'purpose' | 'source' | 'reasons' | 'created_at'>,
): SpendRequest {
  return {
    id,
    currency: 'USD',
    risk_score: 0,
    decision: 'needs_approval',
    matched_rules: fields.reasons.map((r) => r.code),
    paypal_reference: '',
    approval: 'pending',
    ...fields,
  }
}

function pending(
  id: number,
  agent: string,
  request: SpendRequest,
): Approval {
  return {
    id,
    outcome: 'pending',
    agent,
    approver: null,
    note: '',
    created_at: request.created_at,
    decided_at: null,
    spend_request: request,
  }
}

export const mockApprovals: Approval[] = [
  pending(
    101,
    'billing-assistant',
    spendRequest('3f6c1a2e-8b4d-4e1f-9a7c-1d2e3f4a5b6c', {
      amount: '480.00',
      merchant: 'acme.com',
      purpose: 'Invoice email says the account is overdue and must be paid today.',
      source: 'untrusted',
      reasons: [UNTRUSTED, overThreshold('480.00')],
      created_at: minutesAgo(4),
    }),
  ),
  pending(
    102,
    'travel-agent',
    spendRequest('7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d', {
      amount: '89.99',
      merchant: 'acme.com',
      purpose: 'Conference ticket requested by the user.',
      source: 'trusted',
      reasons: [overThreshold('89.99')],
      created_at: minutesAgo(18),
    }),
  ),
  pending(
    103,
    'shopping-bot',
    spendRequest('c4d5e6f7-a8b9-4c0d-9e1f-2a3b4c5d6e7f', {
      amount: '12.50',
      merchant: 'acme.com',
      purpose: '',
      source: 'unknown',
      reasons: [UNKNOWN],
      created_at: minutesAgo(65),
    }),
  ),
  decided(
    pending(
      90,
      'billing-assistant',
      spendRequest('0b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e', {
        amount: '60.00',
        merchant: 'acme.com',
        purpose: 'Monthly hosting bill.',
        source: 'trusted',
        reasons: [overThreshold('60.00')],
        created_at: minutesAgo(60 * 26),
      }),
    ),
    'approved',
    minutesAgo(60 * 25),
  ),
]

function decided(approval: Approval, outcome: 'approved' | 'denied', at: string): Approval {
  return {
    ...approval,
    outcome,
    approver: 'admin',
    decided_at: at,
    spend_request: { ...approval.spend_request, approval: outcome },
  }
}
