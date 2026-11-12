import { apiRequest } from './client'

export interface PayPalPlatformStatus {
  state: 'not_configured' | 'configured' | 'successfully_tested' | 'failed'
  mode: string
  live_payments_enabled: boolean
  client_id_preview: string | null
  webhook_configured: boolean
  webhook_id_preview: string | null
  checkout_enabled: boolean
  payouts_enabled: boolean
  last_attempt_at: number | null
  last_successful_at: number | null
  last_attempt_error: string | null
}

export interface PayPalProbeResponse {
  state: 'successfully_tested' | 'failed'
  latency_ms: number
  tested_at: number
  error: string | null
  message?: string
  retry_after?: number
}

export async function fetchPayPalStatus(signal?: AbortSignal): Promise<PayPalPlatformStatus> {
  return await apiRequest<PayPalPlatformStatus>('/api/settings/paypal/status/', {
    method: 'GET',
    signal,
  })
}

export async function triggerPayPalProbe(signal?: AbortSignal): Promise<PayPalProbeResponse> {
  return await apiRequest<PayPalProbeResponse>('/api/settings/paypal/probe/', {
    method: 'POST',
    body: {},
    signal,
  })
}
