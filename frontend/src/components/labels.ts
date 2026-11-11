import type { ApprovalOutcome, Decision, Source, SpendRequest } from '../api/spendRequests'

export const DECISION_LABELS: Record<
  Decision | 'pending',
  { icon: string; label: string; summary: string }
> = {
  allow: { icon: '✓', label: 'Allowed', summary: 'The policy allowed this request when it was submitted.' },
  deny: { icon: '✕', label: 'Denied', summary: 'The policy denied this request when it was submitted.' },
  needs_approval: {
    icon: '!',
    label: 'Needs approval',
    summary: 'A person must approve this before it is paid.',
  },
  pending: { icon: '…', label: 'Pending', summary: 'No decision yet.' },
}

export const SPEND_STATUS_LABELS: Record<
  SpendRequest['status'],
  { label: string; description: string }
> = {
  pending_approval: {
    label: 'Awaiting human approval',
    description: 'No payment has been executed.',
  },
  denied: {
    label: 'Denied before execution',
    description: 'No payment was sent.',
  },
  approved: {
    label: 'Approved for execution',
    description: 'Payment completion has not been confirmed.',
  },
  executing: {
    label: 'Execution in progress',
    description: 'The payment provider outcome may still be pending.',
  },
  succeeded: {
    label: 'Payment completed',
    description: 'The payment provider reported success.',
  },
  failed: {
    label: 'Execution failed',
    description: 'The payment provider did not report success.',
  },
  execution_blocked: {
    label: 'Execution blocked',
    description: 'Current controls blocked execution. No payment was sent.',
  },
  rejected: {
    label: 'Approval rejected',
    description: 'No payment was sent.',
  },
  expired: {
    label: 'Approval expired',
    description: 'No payment was sent.',
  },
  reversed: {
    label: 'Payment reversed',
    description: 'The payment was later reversed.',
  },
}

export const SOURCE_LABELS: Record<Source, string> = {
  trusted: 'Trusted (operator or user)',
  untrusted: 'Untrusted (web page, email or invoice)',
  web_page: 'Web page',
  email: 'Email',
  invoice: 'Invoice',
  tool_output: 'Tool output',
  unknown: 'Unknown',
}

export const APPROVAL_LABELS: Record<ApprovalOutcome, string> = {
  pending: 'Waiting for a person to decide',
  approved: 'Approved',
  denied: 'Denied by a person',
  expired: 'Expired',
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

/** "4 minutes ago", "yesterday". */
export function timeAgo(iso: string): string {
  const minutes = Math.round((new Date(iso).getTime() - Date.now()) / 60_000)
  if (minutes === 0) return 'just now'
  if (Math.abs(minutes) < 60) return relative.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 24) return relative.format(hours, 'hour')
  return relative.format(Math.round(hours / 24), 'day')
}
