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
  howItWorks: '/how-it-works',
  features: '/features',
  downloads: '/downloads',
  systemRequirements: '/system-requirements',
  install: '/install',
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

// Illustrative landing-page requests; no backend request or payment is made.
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
    result: 'Would be allowed',
    explain: 'This illustrative sample passes the example policy. No backend request or PayPal call is made.',
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
    result: 'Blocked by demo policy',
    explain: 'The example policy blocks this lookalike domain. This is a landing-page illustration, not a live payment request.',
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
    result: 'Would need approval',
    explain: 'The example policy holds this request because its source is untrusted and the amount is high. No backend request is made.',
  },
]

export const STEPS = [
  {
    title: 'The agent asks first',
    body: 'The built-in dashboard demo uses sample requests. The separate Live API tester can send a request to a running AgentGate backend with an agent key.',
  },
  {
    title: 'Rules run in code',
    body: 'Deterministic policy rules check budgets, caps, merchant lists and instruction source. The built-in demo runs these rules locally in the browser.',
  },
  {
    title: 'One clear decision',
    body: 'The result is allow, deny, or needs approval, with reasons for the rules that fired. The demo approval queue is simulated in memory.',
  },
  {
    title: 'Pay and record',
    body: 'The dashboard demo simulates payment outcomes and sample audit activity. It makes no PayPal calls; backend payment execution is separate and defaults to a fake executor.',
  },
]
