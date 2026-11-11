import { apiRequest } from './client'
import { pageQuery, type ListOptions, type Page, type UUID, type IsoDateTime } from './types'

export type AuditActor = 'person' | 'agent' | 'system'
export type AuditActorType = 'user' | 'agent' | 'system' | 'paypal'

export interface AuditEvent {
  id: number
  organization: UUID
  agent: UUID | null
  spend_request: UUID | null
  event_type: string
  actor_type: AuditActorType
  actor_id: string
  payload: Record<string, unknown>
  prev_hash: string
  hash: string
  created_at: IsoDateTime
}

export interface AuditListOptions extends ListOptions {
  event_type?: string
  agent?: UUID
  spend_request?: UUID
  actor?: AuditActor
  actor_type?: AuditActorType
  actor_id?: string
  created_after?: IsoDateTime
  created_before?: IsoDateTime
  after?: number
  ordering?: string
}

export interface AuditVerification {
  checked: number
  organizations: number
}

export function listAuditEvents(
  options: AuditListOptions = {},
): Promise<Page<AuditEvent>> {
  const query = new URLSearchParams(pageQuery(options).slice(1))
  for (const key of [
    'event_type',
    'agent',
    'spend_request',
    'actor',
    'actor_type',
    'actor_id',
    'created_after',
    'created_before',
    'after',
    'ordering',
  ] as const) {
    const value = options[key]
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const suffix = query.toString()
  return apiRequest<Page<AuditEvent>>(`/v1/audit/${suffix ? `?${suffix}` : ''}`, {
    signal: options.signal,
  })
}

export function verifyAudit(signal?: AbortSignal): Promise<AuditVerification> {
  return apiRequest<AuditVerification>('/v1/audit/verify/', { signal })
}
