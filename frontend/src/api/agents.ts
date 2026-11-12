import { apiRequest } from './client'
import { pageQuery, type ListOptions, type Page, type UUID, type IsoDateTime } from './types'

export type AgentStatus = 'active' | 'suspended'

export interface AgentKeyMetadata {
  prefix: string
  created_at: IsoDateTime
  last_used_at: IsoDateTime | null
}

export interface AgentListItem {
  id: UUID
  name: string
  status: AgentStatus
  created_at: IsoDateTime
  updated_at: IsoDateTime
  current_key_prefix: string | null
}

export interface AgentPolicySummary {
  id: UUID
  version: number
  name: string
  currency: string
}

export interface AgentDetail {
  id: UUID
  name: string
  organization: UUID
  organization_name: string
  status: AgentStatus
  created_at: IsoDateTime
  updated_at: IsoDateTime
  current_key: AgentKeyMetadata | null
  current_key_prefix: string | null
  policies: AgentPolicySummary[]
  recent_spend_requests: number
  today_spend_minor: number
  currency: string
}

export interface AgentCreateInput {
  name: string
  /** Resource selector only; the server verifies admin membership. */
  organization: UUID
}

export interface AgentCreateResult {
  id: UUID
  name: string
  organization: UUID
  status: AgentStatus
  created_at: IsoDateTime
  updated_at: IsoDateTime
  /** Shown once by the server; do not persist or log it. */
  api_key: string
}

export interface AgentUpdateInput {
  name?: string
  status?: AgentStatus
}

export interface AgentKeyRotation extends Pick<AgentListItem, 'id' | 'name' | 'status'> {
  current_key: AgentKeyMetadata | null
  api_key: string
}

export interface AgentKeyRevocation extends Pick<AgentListItem, 'id' | 'name' | 'status'> {
  current_key: null
  revoked_key: { prefix: string; revoked_at: IsoDateTime }
}

export function listAgents(options: ListOptions = {}): Promise<Page<AgentListItem>> {
  return apiRequest<Page<AgentListItem>>(`/v1/agents/${pageQuery(options)}`, {
    signal: options.signal,
  })
}

export function getAgent(id: UUID, signal?: AbortSignal): Promise<AgentDetail> {
  return apiRequest<AgentDetail>(`/v1/agents/${encodeURIComponent(id)}/`, { signal })
}

export function createAgent(
  input: AgentCreateInput,
  signal?: AbortSignal,
): Promise<AgentCreateResult> {
  return apiRequest<AgentCreateResult>('/v1/agents/', {
    method: 'POST',
    body: input,
    signal,
  })
}

export function updateAgent(
  id: UUID,
  input: AgentUpdateInput,
  signal?: AbortSignal,
): Promise<AgentDetail> {
  return apiRequest<AgentDetail>(`/v1/agents/${encodeURIComponent(id)}/`, {
    method: 'PATCH',
    body: input,
    signal,
  })
}

export function rotateAgentKey(id: UUID, signal?: AbortSignal): Promise<AgentKeyRotation> {
  return apiRequest<AgentKeyRotation>(`/v1/agents/${encodeURIComponent(id)}/rotate-key/`, {
    method: 'POST',
    signal,
  })
}

export function revokeAgentKey(id: UUID, signal?: AbortSignal): Promise<AgentKeyRevocation> {
  return apiRequest<AgentKeyRevocation>(`/v1/agents/${encodeURIComponent(id)}/revoke-key/`, {
    method: 'POST',
    signal,
  })
}
