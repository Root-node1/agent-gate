import type { ApprovalOutcome, Decision, Source } from '../api/spendRequests'

export const DECISION_LABELS: Record<Decision, { icon: string; label: string; summary: string }> = {
  allow: { icon: '✓', label: 'Allowed', summary: 'This payment can go ahead.' },
  deny: { icon: '✕', label: 'Denied', summary: 'This payment was blocked.' },
  needs_approval: {
    icon: '!',
    label: 'Needs approval',
    summary: 'A person must approve this before it is paid.',
  },
  pending: { icon: '…', label: 'Pending', summary: 'No decision yet.' },
}

export const SOURCE_LABELS: Record<Source, string> = {
  trusted: 'Trusted (operator or user)',
  untrusted: 'Untrusted (web page, email or invoice)',
  unknown: 'Unknown',
}

export const APPROVAL_LABELS: Record<ApprovalOutcome, string> = {
  pending: 'Waiting for a person to decide',
  approved: 'Approved',
  denied: 'Denied by a person',
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString()
}
