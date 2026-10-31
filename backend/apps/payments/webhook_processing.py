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
from apps.payments.checkout.services import (
    CaptureVerificationError,
    _extract_capture,
    _verify_capture,
    _verify_paypal_order,
    get_paypal_order,
)
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

    # Provider lookup outside any database transaction.
    from apps.payments.paypal.client import PayPalClient

    client = PayPalClient.from_settings(django_settings)
    try:
        paypal_order = get_paypal_order(checkout_order=checkout, client=client)
    except PayPalClientError:
        return "retryable"
    if not paypal_order:
        return "retryable"
    try:
        _verify_paypal_order(paypal_order, checkout)
        capture = _extract_capture(paypal_order)
        capture_status = _verify_capture(capture, checkout)
    except CaptureVerificationError:
        return "retryable"
    capture_id = capture.get("id") if capture else None
    if resource.get("id") and capture_id and resource.get("id") != capture_id:
        return "retryable"
    if capture_status != "COMPLETED":
        return "retryable"

    with transaction.atomic():
        locked_event = WebhookEvent.objects.select_for_update().get(pk=webhook_event.pk)
        if locked_event.processed_at is not None:
            return "already_processed"
        checkout = CheckoutOrder.objects.select_for_update().get(pk=checkout.pk)
        if checkout.status == CheckoutOrder.Status.COMPLETED:
            locked_event.processed_at = django_timezone.now()
            locked_event.save(update_fields=["processed_at", "updated_at"])
            return "already_processed"
        if checkout.status not in (
            CheckoutOrder.Status.APPROVED,
            CheckoutOrder.Status.CAPTURE_PENDING,
        ):
            return "retryable"
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
        locked_event.processed_at = django_timezone.now()
        locked_event.save(update_fields=["processed_at", "updated_at"])
    return "processed"


def process_checkout_capture_denied(webhook_event, django_settings):
    resource = (webhook_event.payload or {}).get("resource") or {}
    checkout = _checkout_order_from_resource(resource)
    if checkout is None:
        return "unknown_identifier"
    with transaction.atomic():
        locked_event = WebhookEvent.objects.select_for_update().get(pk=webhook_event.pk)
        if locked_event.processed_at is not None:
            return "already_processed"
        checkout = CheckoutOrder.objects.select_for_update().get(pk=checkout.pk)
        if checkout.status in (
            CheckoutOrder.Status.COMPLETED,
            CheckoutOrder.Status.DECLINED,
        ):
            locked_event.processed_at = django_timezone.now()
            locked_event.save(update_fields=["processed_at", "updated_at"])
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
        locked_event.processed_at = django_timezone.now()
        locked_event.save(update_fields=["processed_at", "updated_at"])
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

    # Binding checks: conflicting identifiers are not applied.
    resource_batch_id = resource.get("payout_batch_id")
    if (
        resource_batch_id
        and reservation.paypal_payout_batch_id
        and str(resource_batch_id) != str(reservation.paypal_payout_batch_id)
    ):
        return "retryable"
    resource_sender_batch_id = resource.get("sender_batch_id")
    if (
        resource_sender_batch_id
        and reservation.sender_batch_id is not None
        and str(resource_sender_batch_id) != str(reservation.sender_batch_id)
    ):
        return "retryable"

    # Provider lookup/reconciliation outside the final DB transaction.
    try:
        result = reconcile_payout(reservation.pk, django_settings)
    except Exception:
        return "retryable"
    if getattr(result, "error", None):
        return "retryable"

    with transaction.atomic():
        locked_event = WebhookEvent.objects.select_for_update().get(pk=webhook_event.pk)
        if locked_event.processed_at is not None:
            return "already_processed"
        reservation = PayoutReservation.objects.select_for_update().get(
            pk=reservation.pk
        )
        if reservation.status in (
            PayoutReservation.Status.COMPLETED,
            PayoutReservation.Status.FAILED,
        ):
            locked_event.processed_at = django_timezone.now()
            locked_event.save(update_fields=["processed_at", "updated_at"])
            return "already_processed"
        # reconcile_payout already applied authoritative state; keep nonterminal
        # reservations recoverable.
        if reservation.status not in (
            PayoutReservation.Status.COMPLETED,
            PayoutReservation.Status.FAILED,
        ):
            reservation.save(update_fields=["status", "updated_at"])
        locked_event.processed_at = django_timezone.now()
        locked_event.save(update_fields=["processed_at", "updated_at"])
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
