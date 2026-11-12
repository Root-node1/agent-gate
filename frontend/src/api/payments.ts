import { apiRequest } from './client'
import type { IsoDateTime, UUID } from './types'

export type CheckoutStatus =
  | 'created'
  | 'payer_action_required'
  | 'approved'
  | 'capture_pending'
  | 'completed'
  | 'declined'
  | 'voided'

export interface CheckoutOrder {
  id: UUID
  organization: UUID
  amount: string
  currency: string
  paypal_order_id: string | null
  paypal_capture_id: string | null
  payer_action_url: string | null
  status: CheckoutStatus
  idempotency_key: UUID
  capture_idempotency_key: UUID | null
  created_at: IsoDateTime
  updated_at: IsoDateTime
}

export interface CreateCheckoutOrderInput {
  /** Resource selector only; the server verifies admin membership. */
  organization: UUID
  amount: string
  currency: string
  idempotency_key: UUID
}

export interface CaptureCheckoutOrderInput {
  capture_idempotency_key: UUID
}

export function createCheckoutOrder(
  input: CreateCheckoutOrderInput,
  signal?: AbortSignal,
): Promise<CheckoutOrder> {
  return apiRequest<CheckoutOrder>('/v1/checkout-orders/', {
    method: 'POST',
    body: input,
    signal,
  })
}

export function captureCheckoutOrder(
  id: UUID,
  input: CaptureCheckoutOrderInput,
  signal?: AbortSignal,
): Promise<CheckoutOrder> {
  return apiRequest<CheckoutOrder>(`/v1/checkout-orders/${encodeURIComponent(id)}/capture/`, {
    method: 'POST',
    body: input,
    signal,
  })
}

export type PayoutReservationStatus =
  | 'reserved'
  | 'submission_pending'
  | 'submitted'
  | 'completed'
  | 'failed'
  | 'uncertain'

export interface PayoutReservation {
  id: UUID
  organization: UUID
  spend_request: UUID
  payee: UUID
  amount: string
  currency: string
  destination_type: string
  destination_value: string
  destination_fingerprint: string
  status: PayoutReservationStatus
  idempotency_key: UUID | null
  paypal_payout_batch_id: string | null
  paypal_payout_item_id: string | null
  created_at: IsoDateTime
  updated_at: IsoDateTime
}

export interface CreatePayoutReservationInput {
  spend_request: UUID
  idempotency_key: UUID
}

export function createPayoutReservation(
  input: CreatePayoutReservationInput,
  signal?: AbortSignal,
): Promise<PayoutReservation> {
  return apiRequest<PayoutReservation>('/v1/payout-reservations/', {
    method: 'POST',
    body: input,
    signal,
  })
}

export function submitPayout(
  id: UUID,
  signal?: AbortSignal,
): Promise<PayoutReservation> {
  return apiRequest<PayoutReservation>(`/v1/payout-reservations/${encodeURIComponent(id)}/submit/`, {
    method: 'POST',
    signal,
  })
}

export function reconcilePayout(
  id: UUID,
  signal?: AbortSignal,
): Promise<PayoutReservation> {
  return apiRequest<PayoutReservation>(`/v1/payout-reservations/${encodeURIComponent(id)}/reconcile/`, {
    signal,
  })
}
