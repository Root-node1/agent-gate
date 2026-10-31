"""Processing of verified PayPal Sandbox webhook inbox events (INT-13L).

This module reconciles existing payment operations from verified inbox events.
It does not create payments, resubmit payouts, execute captures, or mutate
financial state from unverified events.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.audit.models import AuditEvent
from apps.common.money import to_major
from apps.payments.models import CheckoutOrder, WebhookEvent
from apps.payments.payouts.models import PayoutReservation
from apps.payments.payouts.services import reconcile_payout
from apps.payments.paypal.client import PayPalClientError

logger = logging.getLogger(__name__)

_SUPPORTED_EVENTS = frozenset(
    {
        "PAYMENT.CAPTURE.COMPLETED",
        "PAYMENT.CAPTURE.DENIED",
        "PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
        "PAYMENT.PAYOUTS-ITEM.FAILED",
        "PAYMENT.PAYOUTS-ITEM.RETURNED",
        "PAYMENT.PAYOUTS-ITEM.REFUNDED",
        "PAYMENT.PAYOUTS-ITEM.REVERSED",
        "PAYMENT.PAYOUTS-ITEM.BLOCKED",
        "PAYMENT.PAYOUTS-ITEM.CANCELED",
        "PAYMENT.PAYOUTS-ITEM.DENIED",
        "PAYMENT.PAYOUTS-ITEM.ONHOLD",
        "PAYMENT.PAYOUTS-ITEM.PENDING",
        "PAYMENT.PAYOUTS-ITEM.UNCLAIMED",
    }
)

_CHECKOUT_CAPTURE_TERMINAL = frozenset(
    {"COMPLETED", "DENIED", "DECLINED", "REFUNDED", "PARTIALLY_REFUNDED"}
)


def _get_webhook_event(webhook_event, django_settings=None):
    if isinstance(webhook_event, WebhookEvent):
        return webhook_event
    return WebhookEvent.objects.get(pk=webhook_event)


def _mark_processed(webhook_event):
    webhook_event.processed_at = django_timezone.now()
    webhook_event.save(update_fields=["processed_at", "updated_at"])


def _checkout_order_from_resource(resource):
    order_id = None
    supplementary = resource.get("supplementary_data") or {}
    related = supplementary.get("related_ids") or {}
    order_id = related.get("order_id")
    if not order_id:
        order_id = resource.get("custom_id") or resource.get("invoice_id")
    if not order_id:
        return None
    return CheckoutOrder.objects.filter(paypal_order_id=order_id).first()


def _verify_checkout_amount(resource, checkout):
    amount = resource.get("amount") or {}
    currency = amount.get("currency_code")
    value = amount.get("value")
    if currency is None or value is None:
        return True
    if currency != checkout.currency:
        return False
    try:
        remote = Decimal(value)
    except (TypeError, ValueError):
        return False
    local = to_major(checkout.amount_minor, checkout.currency)
    return remote == local


def process_checkout_capture_completed(webhook_event, django_settings):
    resource = (webhook_event.payload or {}).get("resource") or {}
    checkout = _checkout_order_from_resource(resource)
    if checkout is None:
        return "unknown_identifier"
    if not _verify_checkout_amount(resource, checkout):
        return "retryable"

    with transaction.atomic():
        checkout = CheckoutOrder.objects.select_for_update().get(pk=checkout.pk)
        if checkout.status == CheckoutOrder.Status.COMPLETED:
            _mark_processed(webhook_event)
            return "already_processed"
        if checkout.status not in (
            CheckoutOrder.Status.APPROVED,
            CheckoutOrder.Status.CAPTURE_PENDING,
        ):
            # Do not mutate from an out-of-order or incompatible state.
            return "retryable"
        capture_id = resource.get("id")
        if capture_id:
            checkout.paypal_capture_id = capture_id
        checkout.transition_to(CheckoutOrder.Status.COMPLETED)
        checkout.save(update_fields=["paypal_capture_id", "status", "updated_at"])
        AuditEvent.record(
            AuditEvent.EventType.PAYMENT_SUCCEEDED,
            organization=checkout.organization,
            actor_type=AuditEvent.ActorType.PAYPAL,
            actor_id=capture_id or "",
            paypal_order_id=checkout.paypal_order_id,
            paypal_capture_id=capture_id,
            checkout_order_id=str(checkout.pk),
            amount=str(to_major(checkout.amount_minor, checkout.currency)),
            currency=checkout.currency,
        )
    _mark_processed(webhook_event)
    return "processed"


def process_checkout_capture_denied(webhook_event, django_settings):
    resource = (webhook_event.payload or {}).get("resource") or {}
    checkout = _checkout_order_from_resource(resource)
    if checkout is None:
        return "unknown_identifier"
    with transaction.atomic():
        checkout = CheckoutOrder.objects.select_for_update().get(pk=checkout.pk)
        if checkout.status in (
            CheckoutOrder.Status.COMPLETED,
            CheckoutOrder.Status.DECLINED,
        ):
            _mark_processed(webhook_event)
            return "already_processed"
        if checkout.status == CheckoutOrder.Status.CAPTURE_PENDING:
            checkout.transition_to(CheckoutOrder.Status.DECLINED)
            checkout.save(update_fields=["status", "updated_at"])
            AuditEvent.record(
                AuditEvent.EventType.PAYMENT_FAILED,
                organization=checkout.organization,
                actor_type=AuditEvent.ActorType.PAYPAL,
                failure_reason="capture_denied",
                paypal_order_id=checkout.paypal_order_id,
            )
    _mark_processed(webhook_event)
    return "processed"


def _payout_reservation_from_resource(resource):
    item_id = resource.get("payout_item_id")
    batch_id = resource.get("payout_batch_id")
    if item_id:
        reservation = PayoutReservation.objects.filter(
            paypal_payout_item_id=item_id
        ).first()
        if reservation is not None:
            return reservation
    if batch_id:
        return PayoutReservation.objects.filter(paypal_payout_batch_id=batch_id).first()
    return None


def process_payout_event(webhook_event, django_settings):
    resource = (webhook_event.payload or {}).get("resource") or {}
    reservation = _payout_reservation_from_resource(resource)
    if reservation is None:
        return "unknown_identifier"

    item_status = (resource.get("transaction_status") or "").upper()
    # If no authoritative item status is present, reconcile via PayPal GET.
    if not item_status:
        try:
            reconcile_payout(reservation.pk, django_settings)
        except PayPalClientError:
            return "retryable"
        _mark_processed(webhook_event)
        return "processed"

    terminal = reservation.status in (
        PayoutReservation.Status.COMPLETED,
        PayoutReservation.Status.FAILED,
    )

    with transaction.atomic():
        reservation = PayoutReservation.objects.select_for_update().get(
            pk=reservation.pk
        )
        if terminal or reservation.status in (
            PayoutReservation.Status.COMPLETED,
            PayoutReservation.Status.FAILED,
        ):
            _mark_processed(webhook_event)
            return "already_processed"
        if item_status == "SUCCESS":
            reservation.status = PayoutReservation.Status.COMPLETED
            AuditEvent.record(
                AuditEvent.EventType.PAYMENT_SUCCEEDED,
                organization=reservation.organization,
                agent=reservation.spend_request.agent,
                spend_request=reservation.spend_request,
                actor_type=AuditEvent.ActorType.PAYPAL,
                actor_id=resource.get("payout_item_id") or "",
                amount=to_major(reservation.amount_minor, reservation.currency),
                currency=reservation.currency,
                merchant=reservation.spend_request.merchant_ref,
                payout_reservation_id=str(reservation.id),
                paypal_payout_batch_id=reservation.paypal_payout_batch_id,
                paypal_payout_item_id=reservation.paypal_payout_item_id,
            )
        elif item_status in (
            "FAILED",
            "DENIED",
            "CANCELED",
            "REFUNDED",
            "RETURNED",
            "REVERSED",
            "BLOCKED",
        ):
            reservation.status = PayoutReservation.Status.FAILED
            reservation.submission_error = f"PayPal item status: {item_status}"
            AuditEvent.record(
                AuditEvent.EventType.PAYMENT_FAILED,
                organization=reservation.organization,
                agent=reservation.spend_request.agent,
                spend_request=reservation.spend_request,
                actor_type=AuditEvent.ActorType.PAYPAL,
                actor_id=resource.get("payout_item_id") or "",
                amount=to_major(reservation.amount_minor, reservation.currency),
                currency=reservation.currency,
                merchant=reservation.spend_request.merchant_ref,
                payout_reservation_id=str(reservation.id),
                paypal_payout_batch_id=reservation.paypal_payout_batch_id,
                paypal_payout_item_id=reservation.paypal_payout_item_id,
            )
        else:
            # UNCLAIMED, PENDING, ONHOLD, unknown: remain recoverable.
            reservation.status = PayoutReservation.Status.SUBMISSION_PENDING
        reservation.save()

    _mark_processed(webhook_event)
    return "processed"


def process_webhook_event(webhook_event, django_settings, session=None):
    """Process one verified webhook inbox event.

    Returns a status string: ``processed``, ``already_processed``,
    ``ignored``, ``unknown_identifier``, or ``retryable``.
    """
    webhook_event = _get_webhook_event(webhook_event, django_settings)

    # Concurrency guard: lock the inbox row.
    with transaction.atomic():
        locked = WebhookEvent.objects.select_for_update().get(pk=webhook_event.pk)
        if not locked.signature_verified:
            return "unverified"
        if locked.processed_at is not None:
            return "already_processed"
        # Copy needed fields before releasing lock; processing below may be
        # long-running but does not hold this transaction.
        event_type = locked.event_type
        payload = locked.payload
        pk = locked.pk
        webhook_event = locked

    if event_type not in _SUPPORTED_EVENTS:
        # Unsupported events are safely classified and marked processed.
        with transaction.atomic():
            locked = WebhookEvent.objects.select_for_update().get(pk=pk)
            if locked.processed_at is None:
                _mark_processed(locked)
        return "ignored"

    # Reconstruct a lightweight event object for helpers.
    class _Event:
        pass

    evt = _Event()
    evt.payload = payload
    evt.pk = pk

    event_type_upper = event_type.upper()
    if event_type_upper == "PAYMENT.CAPTURE.COMPLETED":
        result = process_checkout_capture_completed(evt, django_settings)
    elif event_type_upper == "PAYMENT.CAPTURE.DENIED":
        result = process_checkout_capture_denied(evt, django_settings)
    elif event_type_upper.startswith("PAYMENT.PAYOUTS-ITEM."):
        result = process_payout_event(evt, django_settings)
    else:
        result = "ignored"

    if result in ("unknown_identifier", "retryable"):
        # Leave unprocessed for retry.
        return result
    with transaction.atomic():
        locked = WebhookEvent.objects.select_for_update().get(pk=pk)
        if locked.processed_at is None:
            _mark_processed(locked)
    return result


def process_paypal_webhook(*args, **kwargs):
    return process_webhook_event(*args, **kwargs)


def process_webhook_events(*, limit=100, django_settings):
    results = []
    queryset = WebhookEvent.objects.filter(
        signature_verified=True, processed_at__isnull=True
    ).order_by("received_at")[:limit]
    for event in queryset:
        results.append(process_webhook_event(event, django_settings))
    return results
