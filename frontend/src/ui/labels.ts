// Display labels for every status in the dashboard. Each status pairs a tone
// (color) with an icon and a word, so nothing relies on color alone.

import type {
  AgentStatus,
  ApprovalOutcome,
  AuditEventType,
  Decision,
  PaymentStatus,
  Role,
  Source,
} from '../demo/types'

export type Tone = 'allow' | 'deny' | 'approval' | 'info' | 'neutral'

export interface StatusLabel {
  tone: Tone
  icon: string
  label: string
}

export const DECISION: Record<Decision, StatusLabel & { summary: string }> = {
  allow: { tone: 'allow', icon: '✓', label: 'Allowed', summary: 'Passed every rule.' },
  deny: { tone: 'deny', icon: '✕', label: 'Denied', summary: 'Broke a hard rule, so it was blocked.' },
  needs_approval: {
    tone: 'approval',
    icon: '!',
    label: 'Needs approval',
    summary: 'A person must approve this before it is paid.',
  },
  pending: { tone: 'neutral', icon: '…', label: 'Pending', summary: 'No decision yet.' },
}

/** Simulated payment results in the in-memory dashboard demo. */
export const PAYMENT: Record<PaymentStatus, StatusLabel & { summary: string }> = {
  not_sent: { tone: 'neutral', icon: '–', label: 'Not sent', summary: 'No PayPal call was made in this demo.' },
  awaiting_approval: {
    tone: 'neutral',
    icon: '⏸',
    label: 'On hold',
    summary: 'Held for a person in the demo; no PayPal call was made.',
  },
  processing: { tone: 'info', icon: '↻', label: 'Simulating', summary: 'Demo only; no PayPal request was sent.' },
  completed: {
    tone: 'allow',
    icon: '✓',
    label: 'Simulated paid',
    summary: 'Demo-only simulated success; no payment was made.',
  },
  failed: {
    tone: 'deny',
    icon: '✕',
    label: 'Simulated failure',
    summary: 'Demo-only simulated failure; no PayPal request was sent.',
  },
}

export const APPROVAL: Record<ApprovalOutcome, StatusLabel> = {
  pending: { tone: 'approval', icon: '⏳', label: 'Waiting' },
  approved: { tone: 'allow', icon: '✓', label: 'Approved' },
  denied: { tone: 'deny', icon: '✕', label: 'Denied' },
  expired: { tone: 'neutral', icon: '⌛', label: 'Expired' },
}

export const AGENT_STATUS: Record<AgentStatus, StatusLabel> = {
  active: { tone: 'allow', icon: '●', label: 'Active' },
  suspended: { tone: 'deny', icon: '⏻', label: 'Suspended' },
}

export const SOURCE: Record<Source, { label: string; short: string }> = {
  trusted: { label: 'Trusted (operator or user)', short: 'Trusted' },
  untrusted: { label: 'Untrusted (web page, email or invoice)', short: 'Untrusted' },
  web_page: { label: 'Web page', short: 'Web page' },
  email: { label: 'Email', short: 'Email' },
  invoice: { label: 'Invoice', short: 'Invoice' },
  tool_output: { label: 'Tool output', short: 'Tool output' },
  unknown: { label: 'Unknown', short: 'Unknown' },
}

export const ROLE: Record<Role, { label: string; description: string }> = {
  admin: { label: 'Admin', description: 'Manages agents, policies, keys and the team.' },
  approver: { label: 'Approver', description: 'Approves or denies payments in the queue.' },
  viewer: { label: 'Viewer', description: 'Read-only access to activity and the audit log.' },
}

export const EVENT: Record<AuditEventType, { label: string; tone: Tone }> = {
  'spend_request.received': { label: 'Request received', tone: 'neutral' },
  'spend_request.decided': { label: 'Decision made', tone: 'info' },
  'approval.requested': { label: 'Approval requested', tone: 'approval' },
  'approval.approved': { label: 'Approval granted', tone: 'allow' },
  'approval.denied': { label: 'Approval denied', tone: 'deny' },
  'approval.expired': { label: 'Approval expired', tone: 'neutral' },
  'payment.processing': { label: 'Simulated payment', tone: 'info' },
  'payment.completed': { label: 'Simulated payment success', tone: 'allow' },
  'payment.failed': { label: 'Simulated payment failure', tone: 'deny' },
  'agent.created': { label: 'Agent registered', tone: 'neutral' },
  'agent.suspended': { label: 'Agent suspended', tone: 'deny' },
  'agent.reactivated': { label: 'Agent reactivated', tone: 'allow' },
  'agent.key_created': { label: 'API key created', tone: 'neutral' },
  'agent.key_revoked': { label: 'API key revoked', tone: 'deny' },
  'policy.updated': { label: 'Policy updated', tone: 'info' },
}

export const EVENT_GROUPS: { label: string; types: AuditEventType[] }[] = [
  { label: 'Requests', types: ['spend_request.received', 'spend_request.decided'] },
  { label: 'Approvals', types: ['approval.requested', 'approval.approved', 'approval.denied', 'approval.expired'] },
  { label: 'Payments', types: ['payment.processing', 'payment.completed', 'payment.failed'] },
  {
    label: 'Agents and policies',
    types: ['agent.created', 'agent.suspended', 'agent.reactivated', 'agent.key_created', 'agent.key_revoked', 'policy.updated'],
  },
]
