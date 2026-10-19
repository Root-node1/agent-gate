// Approval queue API. The backend endpoints do not exist yet, so this module
// serves mock data from ./mockApprovals. When they land, replace the bodies of
// these functions with fetch calls; the pages only depend on these signatures.
//
// Expected endpoints (Doc.md section 5, plus a list endpoint we still need):
//   GET  /v1/approvals/?outcome=pending
//   POST /v1/approvals/{id}/approve   { note }
//   POST /v1/approvals/{id}/deny      { note }

import { ApiError, type ApprovalOutcome, type SpendRequest } from './spendRequests'
import { mockApprovals } from './mockApprovals'

export const USING_MOCK_DATA = true

export interface Approval {
  id: number
  outcome: ApprovalOutcome
  /** Name of the agent that sent the request. */
  agent: string
  /** Username of the person who decided, once decided. */
  approver: string | null
  note: string
  created_at: string
  decided_at: string | null
  spend_request: SpendRequest
}

const LATENCY_MS = 400
const wait = () => new Promise((resolve) => setTimeout(resolve, LATENCY_MS))

// Module-level copy so decisions persist while the tab is open.
let store: Approval[] = structuredClone(mockApprovals)

export async function listApprovals(): Promise<Approval[]> {
  await wait()
  return structuredClone(store)
}

async function decide(id: number, outcome: 'approved' | 'denied', note: string) {
  await wait()
  const approval = store.find((a) => a.id === id)
  if (!approval) throw new ApiError('This approval no longer exists.', 404)
  if (approval.outcome !== 'pending') {
    throw new ApiError('Someone already decided this payment. Refresh the list.', 409)
  }
  const updated: Approval = {
    ...approval,
    outcome,
    note: note.trim(),
    approver: 'you',
    decided_at: new Date().toISOString(),
    spend_request: { ...approval.spend_request, approval: outcome },
  }
  store = store.map((a) => (a.id === id ? updated : a))
  return structuredClone(updated)
}

export function approve(id: number, note: string): Promise<Approval> {
  return decide(id, 'approved', note)
}

export function deny(id: number, note: string): Promise<Approval> {
  return decide(id, 'denied', note)
}
