import { budgetUsage } from '../../../demo/selectors'
import type { DemoState } from '../../../demo/types'

export const AGENT_NAME_PATTERN = /^[a-z0-9][a-z0-9-]{1,48}$/

/** Client-side check that matches createAgent, so errors show before submit. */
export function agentNameError(name: string, taken: string[]): string | null {
  const clean = name.trim()
  if (!clean) return 'Enter a name.'
  if (!AGENT_NAME_PATTERN.test(clean)) return 'Use 2 to 50 lowercase letters, numbers or dashes. Start with a letter or number.'
  if (taken.includes(clean)) return 'An agent with this name already exists.'
  return null
}

export interface AgentActivity {
  lastRequestAt: string | null
  requestsToday: number
  requestsMonth: number
  spendToday: number
  spendMonth: number
  currency: string
}

export function agentActivity(s: DemoState, agentId: number, now: number): AgentActivity {
  const at = new Date(now)
  const dayStart = new Date(at.getFullYear(), at.getMonth(), at.getDate()).getTime()
  const monthStart = new Date(at.getFullYear(), at.getMonth(), 1).getTime()
  let requestsToday = 0
  let requestsMonth = 0
  let lastRequestAt: string | null = null
  for (const r of s.requests) {
    if (r.agent_id !== agentId) continue
    const t = new Date(r.created_at).getTime()
    if (t >= dayStart) requestsToday++
    if (t >= monthStart) requestsMonth++
    if (!lastRequestAt || r.created_at > lastRequestAt) lastRequestAt = r.created_at
  }
  const usage = budgetUsage(s, agentId, at)
  return {
    lastRequestAt,
    requestsToday,
    requestsMonth,
    spendToday: usage?.today ?? 0,
    spendMonth: usage?.month ?? 0,
    currency: usage?.currency ?? 'USD',
  }
}

export const API_ENDPOINT = 'POST /v1/spend-requests/'

export function curlSnippet(rawKey: string) {
  return [
    'curl -X POST https://agentgate.example.com/v1/spend-requests/ \\',
    `  -H "Authorization: Bearer ${rawKey}" \\`,
    '  -H "Content-Type: application/json" \\',
    `  -d '{"amount": "25.00", "currency": "USD", "merchant": "github.com",`,
    `       "purpose": "Team seats", "source": "trusted"}'`,
  ].join('\n')
}
