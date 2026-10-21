// Copy and data for the landing page. Kept out of the component files so they
// only export components (react-refresh/only-export-components).

export const LINKS = {
  github: 'https://github.com/Root-node1/agent-gate',
  readme: 'https://github.com/Root-node1/agent-gate#readme',
  design: 'https://github.com/Root-node1/agent-gate/blob/main/Doc.md',
  demo: '/app',
  simulate: '/app/simulate',
  approvals: '/app/approvals',
  audit: '/app/audit',
}

export type Outcome = 'allow' | 'deny' | 'needs_approval'

export interface Scenario {
  outcome: Outcome
  label: string
  amount: string
  merchant: string
  source: 'trusted' | 'untrusted'
  sourceLabel: string
  purpose: string
  codes: string[]
  result: string
  explain: string
}

// Example requests, checked against a policy with a $500 per-transaction cap,
// a $100 approval threshold and paypa1-secure.net on the block list.
export const SCENARIOS: Scenario[] = [
  {
    outcome: 'allow',
    label: 'Allowed',
    amount: '$36.00',
    merchant: 'github.com',
    source: 'trusted',
    sourceLabel: 'Trusted (user prompt)',
    purpose: 'GitHub Team seat',
    codes: [],
    result: 'Sent to PayPal',
    explain: 'Trusted source, known merchant, under every limit. The payment goes ahead.',
  },
  {
    outcome: 'deny',
    label: 'Denied',
    amount: '$89.00',
    merchant: 'paypa1-secure.net',
    source: 'untrusted',
    sourceLabel: 'Untrusted (web page)',
    purpose: 'Verify account',
    codes: ['MERCHANT_BLOCKED', 'UNTRUSTED_SOURCE'],
    result: 'Blocked at the gate',
    explain: 'A lookalike domain on the block list. Hard rules win, so no human is even asked.',
  },
  {
    outcome: 'needs_approval',
    label: 'Needs approval',
    amount: '$480.00',
    merchant: 'aws.amazon.com',
    source: 'untrusted',
    sourceLabel: 'Untrusted (invoice email)',
    purpose: 'Pay overdue invoice',
    codes: ['UNTRUSTED_SOURCE', 'OVER_APPROVAL_THRESHOLD'],
    result: 'Held for a human',
    explain: 'A real merchant, but the instruction came from an email and the amount is high. A person decides.',
  },
]

export const STEPS = [
  {
    title: 'The agent asks first',
    body: 'Before paying, your agent sends a spend request with its own API key: amount, merchant, purpose and where the instruction came from.',
  },
  {
    title: 'Rules run in code',
    body: 'AgentGate checks the request against the agent’s policy: budgets, caps, merchant lists and source. Same input, same answer, every time.',
  },
  {
    title: 'One clear decision',
    body: 'Allow, deny, or needs approval, with a reason code for every rule that fired. Approvals wait in a queue for a person.',
  },
  {
    title: 'Pay and record',
    body: 'Approved payments go to PayPal (sandbox today). Every decision and action is written to an append-only audit log.',
  },
]
