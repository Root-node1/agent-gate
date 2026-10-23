export const SETTINGS_TABS = [
  { id: 'workspace', label: 'Workspace' },
  { id: 'paypal', label: 'PayPal' },
  { id: 'keys', label: 'API keys' },
  { id: 'team', label: 'Team and roles' },
  { id: 'developers', label: 'Developers' },
] as const

export type SettingsTab = (typeof SETTINGS_TABS)[number]['id']

export function isSettingsTab(value: string | null): value is SettingsTab {
  return SETTINGS_TABS.some((t) => t.id === value)
}

export const CURRENCIES = [
  { code: 'USD', label: 'US dollar (USD)' },
  { code: 'EUR', label: 'Euro (EUR)' },
  { code: 'GBP', label: 'British pound (GBP)' },
  { code: 'KES', label: 'Kenyan shilling (KES)' },
]

export const EXPIRY_OPTIONS = [
  { hours: 1, label: '1 hour' },
  { hours: 4, label: '4 hours' },
  { hours: 24, label: '24 hours' },
  { hours: 72, label: '3 days' },
]

const COMMON_ZONES = [
  'UTC',
  'Africa/Nairobi',
  'Africa/Lagos',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'America/Chicago',
  'America/Los_Angeles',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Australia/Sydney',
]

export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

export function timezoneOptions(): string[] {
  const zone = browserTimezone()
  return COMMON_ZONES.includes(zone) ? COMMON_ZONES : [zone, ...COMMON_ZONES]
}

export interface WorkspaceSettings {
  name: string
  currency: string
  expiryHours: number
  timezone: string
}

export function defaultWorkspace(): WorkspaceSettings {
  return { name: 'AgentGate Demo', currency: 'USD', expiryHours: 24, timezone: browserTimezone() }
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function isEmail(value: string): boolean {
  return EMAIL.test(value)
}

export const BACKEND_DEV_URL = 'http://127.0.0.1:8000'
export const GITHUB_URL = 'https://github.com/Root-node1/agent-gate'

export const CURL_EXAMPLE = `curl -X POST ${BACKEND_DEV_URL}/v1/spend-requests/ \\
  -H "Authorization: Bearer agk_YOUR_AGENT_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "amount": "42.00",
    "currency": "USD",
    "merchant": "openai.com",
    "purpose": "API credits for the research agent",
    "source": "trusted"
  }'`
