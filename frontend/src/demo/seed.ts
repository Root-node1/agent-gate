// Seeded demo data: four agents, their policies, two weeks of requests and
// the matching audit trail. Requests go through the real rule engine
// (recordRequest), so every decision and reason is consistent with policy.
// A fixed random seed keeps the history the same on every load.

import {
  addEvent,
  recordRequest,
  settlePayment,
  type Draft,
  type SubmitInput,
} from './store'
import type { Agent, DemoState, Policy, TeamMember } from './types'

const HISTORY_DAYS = 14

/** mulberry32: small deterministic PRNG. */
function prng(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const TEAM: TeamMember[] = [
  { id: 1, name: 'Demo Admin', email: 'admin@agentgate.dev', role: 'admin' },
  { id: 2, name: 'Alex Kamau', email: 'alex@agentgate.dev', role: 'approver' },
  { id: 3, name: 'Jordan Njeri', email: 'jordan@agentgate.dev', role: 'viewer' },
]

interface Template {
  merchant: string
  purpose: string
  min: number
  max: number
  source?: SubmitInput['source']
}

interface AgentSeed {
  agent: Omit<Agent, 'created_at' | 'last_used_at'>
  policy: Omit<Policy, 'id' | 'agent_id' | 'updated_at'>
  perDay: [number, number]
  templates: Template[]
}

const AGENTS: AgentSeed[] = [
  {
    agent: {
      id: 1,
      name: 'billing-assistant',
      description: 'Pays recurring software and infrastructure bills.',
      status: 'active',
      api_key_prefix: 'agk_b7Qx',
    },
    policy: {
      name: 'Infrastructure bills',
      currency: 'USD',
      per_transaction_cap: 500,
      approval_threshold: 150,
      daily_budget: 1000,
      monthly_budget: 8000,
      allowed_merchants: ['aws.amazon.com', 'digitalocean.com', 'github.com', 'figma.com', 'notion.so'],
      blocked_merchants: [],
    },
    perDay: [1, 3],
    templates: [
      { merchant: 'aws.amazon.com', purpose: 'EC2 and S3 usage', min: 40, max: 140 },
      { merchant: 'digitalocean.com', purpose: 'Droplet hosting', min: 12, max: 60 },
      { merchant: 'github.com', purpose: 'Team seats', min: 21, max: 84 },
      { merchant: 'figma.com', purpose: 'Design seats', min: 15, max: 45 },
      { merchant: 'notion.so', purpose: 'Workspace plan', min: 10, max: 30 },
      { merchant: 'aws.amazon.com', purpose: 'Reserved instance renewal', min: 160, max: 320 },
      { merchant: 'aws.amazon.com', purpose: '3-year savings plan', min: 520, max: 700 },
    ],
  },
  {
    agent: {
      id: 2,
      name: 'travel-agent',
      description: 'Books flights, hotels and rides for the team.',
      status: 'active',
      api_key_prefix: 'agk_T3vp',
    },
    policy: {
      name: 'Team travel',
      currency: 'USD',
      per_transaction_cap: 1200,
      approval_threshold: 400,
      daily_budget: 2500,
      monthly_budget: 15000,
      allowed_merchants: [],
      blocked_merchants: ['cheap-flights-deals.biz'],
    },
    perDay: [0, 2],
    templates: [
      { merchant: 'booking.com', purpose: 'Hotel for client visit', min: 90, max: 380 },
      { merchant: 'uber.com', purpose: 'Airport ride', min: 12, max: 45 },
      { merchant: 'kenya-airways.com', purpose: 'Return flight NBO to MBA', min: 120, max: 360 },
      { merchant: 'delta.com', purpose: 'Conference flight', min: 420, max: 900 },
      { merchant: 'cheap-flights-deals.biz', purpose: 'Deal from a newsletter', min: 80, max: 200, source: 'untrusted' },
    ],
  },
  {
    agent: {
      id: 3,
      name: 'shopping-bot',
      description: 'Restocks office supplies.',
      status: 'active',
      api_key_prefix: 'agk_s9Lm',
    },
    policy: {
      name: 'Office supplies',
      currency: 'USD',
      per_transaction_cap: 100,
      approval_threshold: 50,
      daily_budget: 300,
      monthly_budget: 2000,
      allowed_merchants: ['acme.com', 'officesupply.com', 'staples.com'],
      blocked_merchants: ['evil.com', 'paypa1-secure.net'],
    },
    perDay: [1, 4],
    templates: [
      { merchant: 'officesupply.com', purpose: 'Printer paper and toner', min: 8, max: 45 },
      { merchant: 'staples.com', purpose: 'Notebooks and pens', min: 5, max: 30 },
      { merchant: 'acme.com', purpose: 'Coffee and snacks', min: 10, max: 48 },
      { merchant: 'acme.com', purpose: 'Standing desk mat', min: 55, max: 95 },
      { merchant: 'amazon.com', purpose: 'Cheaper option found online', min: 15, max: 40 },
    ],
  },
  {
    agent: {
      id: 4,
      name: 'research-scraper',
      description: 'Buys datasets and API credits. Suspended after unusual requests.',
      status: 'active',
      api_key_prefix: 'agk_r2Dn',
    },
    policy: {
      name: 'Research data',
      currency: 'USD',
      per_transaction_cap: 200,
      approval_threshold: 75,
      daily_budget: 400,
      monthly_budget: 3000,
      allowed_merchants: ['kaggle.com', 'datarade.ai', 'rapidapi.com'],
      blocked_merchants: [],
    },
    perDay: [0, 2],
    templates: [
      { merchant: 'rapidapi.com', purpose: 'API credits', min: 10, max: 60 },
      { merchant: 'datarade.ai', purpose: 'Market dataset', min: 50, max: 180 },
      { merchant: 'free-data-dump.ru', purpose: 'Dataset link found on a forum', min: 30, max: 90, source: 'untrusted' },
    ],
  },
]

/** Days ago (0 = today) at a given hour and minute, never in the future. */
function at(now: Date, daysAgo: number, hour: number, minute: number) {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - daysAgo, hour, minute)
  return d > now ? null : d
}

function minutesBefore(now: Date, minutes: number) {
  return new Date(now.getTime() - minutes * 60_000)
}

export function buildSeed(): DemoState {
  const now = new Date()
  const random = prng(20261018)
  const pick = <T,>(items: T[]) => items[Math.floor(random() * items.length)]
  const between = (min: number, max: number) => Math.round((min + random() * (max - min)) * 100) / 100

  const firstDay = new Date(now.getFullYear(), now.getMonth(), now.getDate() - HISTORY_DAYS - 7)
  const draft: Draft = {
    state: {
      agents: AGENTS.map((s) => ({ ...s.agent, created_at: firstDay.toISOString(), last_used_at: null })),
      policies: AGENTS.map((s, i) => ({
        ...s.policy,
        id: i + 1,
        agent_id: s.agent.id,
        updated_at: firstDay.toISOString(),
      })),
      requests: [],
      approvals: [],
      events: [],
      team: TEAM,
      currentUser: TEAM[0],
    },
    nextEventId: 1,
  }
  const agentById = (id: number) => draft.state.agents.find((a) => a.id === id)!

  for (const s of AGENTS) {
    const created_at = firstDay.toISOString()
    addEvent(draft, 'agent.created', { actor: TEAM[0].email, agent_id: s.agent.id, created_at })
    addEvent(draft, 'agent.key_created', {
      actor: TEAM[0].email,
      agent_id: s.agent.id,
      created_at,
      payload: { key_prefix: s.agent.api_key_prefix },
    })
  }

  // 1. History: generated requests, processed in time order.
  const planned: { agentId: number; when: Date; input: SubmitInput; leavePending?: boolean }[] = [
    // Nobody answered this one in time, so it expires.
    {
      agentId: 2,
      when: minutesBefore(now, 2 * 24 * 60 + 200),
      input: {
        amount: 455,
        currency: 'USD',
        merchant: 'booking.com',
        purpose: 'Hotel upgrade suggested by the booking site',
        source: 'trusted',
      },
      leavePending: true,
    },
  ]
  for (let day = HISTORY_DAYS - 1; day >= 0; day--) {
    for (const s of AGENTS) {
      // research-scraper is suspended 3 days ago and sends nothing after.
      if (s.agent.id === 4 && day < 3) continue
      const count = s.perDay[0] + Math.floor(random() * (s.perDay[1] - s.perDay[0] + 1))
      for (let i = 0; i < count; i++) {
        const when = at(now, day, 8 + Math.floor(random() * 11), Math.floor(random() * 60))
        // Leave the last two hours for the scripted requests below.
        if (!when || when > minutesBefore(now, 120)) continue
        const t = pick(s.templates)
        planned.push({
          agentId: s.agent.id,
          when,
          input: {
            amount: between(t.min, t.max),
            currency: 'USD',
            merchant: t.merchant,
            purpose: t.purpose,
            source: t.source ?? (random() < 0.08 ? 'unknown' : 'trusted'),
          },
        })
      }
    }
  }
  planned.sort((a, b) => a.when.getTime() - b.when.getTime())

  for (const p of planned) {
    const request = recordRequest(draft, agentById(p.agentId), p.input, p.when)
    if (request.decision === 'allow') {
      settlePayment(draft, request.id, new Date(p.when.getTime() + 3000), random() > 0.05)
    }
    if (request.decision === 'needs_approval') {
      const approval = draft.state.approvals.find((a) => a.spend_request_id === request.id)!
      const roll = random()
      // A few are left to expire; the rest are decided within a couple of hours.
      if (p.leavePending || roll < 0.08) continue
      const decidedAt = new Date(p.when.getTime() + (10 + random() * 120) * 60_000)
      if (decidedAt > now) continue
      const approver = pick([TEAM[0], TEAM[1]])
      approval.outcome = roll < 0.78 ? 'approved' : 'denied'
      approval.approver = approver.email
      approval.decided_at = decidedAt.toISOString()
      approval.note =
        approval.outcome === 'approved'
          ? pick(['', 'Expected renewal.', 'Checked with the team.', ''])
          : pick(['Not a vendor we use.', 'Looks like a phishing link.', 'Too expensive, find another option.'])
      addEvent(draft, approval.outcome === 'approved' ? 'approval.approved' : 'approval.denied', {
        actor: approver.email,
        agent_id: p.agentId,
        spend_request_id: request.id,
        created_at: approval.decided_at,
        payload: approval.note ? { note: approval.note } : {},
      })
      if (approval.outcome === 'approved') {
        request.payment_status = 'processing'
        addEvent(draft, 'payment.processing', {
          actor: 'AgentGate',
          agent_id: p.agentId,
          spend_request_id: request.id,
          created_at: approval.decided_at,
        })
        settlePayment(draft, request.id, new Date(decidedAt.getTime() + 3000), random() > 0.05)
      } else {
        request.payment_status = 'not_sent'
      }
    }
  }

  // Expire pending approvals older than the time limit.
  for (const approval of draft.state.approvals) {
    if (approval.outcome !== 'pending' || new Date(approval.expires_at) > now) continue
    approval.outcome = 'expired'
    approval.decided_at = approval.expires_at
    const request = draft.state.requests.find((r) => r.id === approval.spend_request_id)!
    request.payment_status = 'not_sent'
    addEvent(draft, 'approval.expired', {
      actor: 'AgentGate',
      agent_id: request.agent_id,
      spend_request_id: request.id,
      created_at: approval.expires_at,
    })
  }

  // research-scraper was suspended 3 days ago.
  const scraper = agentById(4)
  scraper.status = 'suspended'
  addEvent(draft, 'agent.suspended', {
    actor: TEAM[0].email,
    agent_id: 4,
    created_at: minutesBefore(now, 3 * 24 * 60 - 30).toISOString(),
    payload: { note: 'Tried to buy data from an unknown site.' },
  })

  // 2. Scripted recent requests so the demo always has a story to tell.
  const scripted: { agentId: number; minutesAgo: number; input: SubmitInput }[] = [
    {
      agentId: 3,
      minutesAgo: 95,
      input: { amount: 24.5, currency: 'USD', merchant: 'officesupply.com', purpose: 'Printer toner', source: 'trusted' },
    },
    {
      agentId: 2,
      minutesAgo: 70,
      input: { amount: 640, currency: 'USD', merchant: 'delta.com', purpose: 'Flight to the PayPal developer summit', source: 'trusted' },
    },
    {
      agentId: 3,
      minutesAgo: 48,
      input: {
        amount: 89,
        currency: 'USD',
        merchant: 'paypa1-secure.net',
        purpose: 'Email said our PayPal account is locked and asked for a verification payment.',
        source: 'untrusted',
      },
    },
    {
      agentId: 1,
      minutesAgo: 22,
      input: {
        amount: 480,
        currency: 'USD',
        merchant: 'aws.amazon.com',
        purpose: 'Invoice email: "URGENT: account overdue, pay immediately to avoid shutdown."',
        source: 'untrusted',
      },
    },
    {
      agentId: 1,
      minutesAgo: 9,
      input: { amount: 36, currency: 'USD', merchant: 'github.com', purpose: 'Copilot seats', source: 'trusted' },
    },
    {
      agentId: 3,
      minutesAgo: 4,
      input: { amount: 18.75, currency: 'USD', merchant: 'staples.com', purpose: 'Sticky notes', source: 'unknown' },
    },
  ]
  for (const s of scripted) {
    const when = minutesBefore(now, s.minutesAgo)
    const request = recordRequest(draft, agentById(s.agentId), s.input, when)
    if (request.decision === 'allow') settlePayment(draft, request.id, new Date(when.getTime() + 3000))
  }

  // Keep every list newest first, with event ids in time order.
  const byTimeDesc = <T extends { created_at: string }>(a: T, b: T) => b.created_at.localeCompare(a.created_at)
  draft.state.requests.sort(byTimeDesc)
  draft.state.approvals.sort(byTimeDesc)
  draft.state.events.sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id)
  draft.state.events.forEach((e, i) => (e.id = i + 1))
  draft.state.events.reverse()

  return draft.state
}

