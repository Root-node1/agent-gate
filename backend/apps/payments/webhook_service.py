"""Apply verified PayPal webhook events to spend requests."""

from __future__ import annotations

import json
import logging

from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.payments.paypal.client import (
    PayPalAPIError,
    PayPalTimeoutError,
    PayPalClient,
    PayPalClientError,
    PayPalTransportError,
)
from apps.payments.paypal.config import PayPalConfigError, get_paypal_config
from apps.spend.models import SpendRequest

from .models import WebhookEvent
from .paypal.webhooks import (
    OUTCOME_FAILED,
    OUTCOME_REVERSED,
    OUTCOME_SUCCEEDED,
    parse_payout_event,
)
from .services import lock_agent_and_spend

logger = logging.getLogger(__name__)

OUTCOME_STATUS = {
    OUTCOME_SUCCEEDED: SpendRequest.Status.SUCCEEDED,
    OUTCOME_FAILED: SpendRequest.Status.FAILED,
    OUTCOME_REVERSED: SpendRequest.Status.REVERSED,
}
OUTCOME_AUDIT = {
    OUTCOME_SUCCEEDED: AuditEvent.EventType.PAYMENT_SUCCEEDED,
    OUTCOME_FAILED: AuditEvent.EventType.PAYMENT_FAILED,
    OUTCOME_REVERSED: AuditEvent.EventType.PAYMENT_REVERSED,
}
STATUS_RANK = {
    SpendRequest.Status.PENDING_APPROVAL: 0,
    SpendRequest.Status.DENIED: 0,
    SpendRequest.Status.APPROVED: 1,
    SpendRequest.Status.EXECUTING: 2,
    SpendRequest.Status.SUCCEEDED: 3,
    SpendRequest.Status.FAILED: 3,
    SpendRequest.Status.REJECTED: 3,
    SpendRequest.Status.EXPIRED: 3,
    SpendRequest.Status.REVERSED: 4,
}
TERMINAL_STATUSES = frozenset(
    {
        SpendRequest.Status.SUCCEEDED,
        SpendRequest.Status.FAILED,
        SpendRequest.Status.REVERSED,
    }
)
APPLICABLE_STATUSES = frozenset(
    {
        SpendRequest.Status.APPROVED,
        SpendRequest.Status.EXECUTING,
        SpendRequest.Status.SUCCEEDED,
        SpendRequest.Status.FAILED,
    }
)


def should_apply(current_status: str, target_status: str) -> bool:
    """Return whether a provider status moves the request forward."""
    return STATUS_RANK.get(target_status, -1) > STATUS_RANK.get(current_status, -1)


def apply_webhook_event(webhook_event_id) -> str:
    """Process one stored event once, updating the spend request and audit log."""
    with transaction.atomic():
        event = WebhookEvent.objects.select_for_update().get(pk=webhook_event_id)
        if event.processed_at is not None:
            return "already_processed"
        if not event.signature_verified:
            raise PermissionError(
                "Unverified webhook events cannot be processed."
            )

        parsed = parse_payout_event(event.payload)
        now = timezone.now()
        if parsed.spend_request_id is None:
            _mark_processed(event, now)
            logger.warning(
                "Webhook event %s does not reference a spend request.",
                event.paypal_event_id,
            )
            return "ignored"

        try:
            agent, spend_request = lock_agent_and_spend(parsed.spend_request_id)
        except SpendRequest.DoesNotExist:
            _mark_processed(event, now)
            logger.warning(
                "Webhook event %s references an unknown spend request.",
                event.paypal_event_id,
            )
            return "ignored"

        target_status = OUTCOME_STATUS.get(parsed.outcome or "")
        applied = False
        reason = ""

        if target_status is None:
            reason = "unsupported_event"
        elif spend_request.status not in APPLICABLE_STATUSES:
            reason = "unexpected_state"
        elif (
            parsed.reference
            and spend_request.paypal_reference
            and parsed.reference != spend_request.paypal_reference
        ):
            reason = "reference_mismatch"
        elif not should_apply(spend_request.status, target_status):
            reason = "not_forward"
        else:
            spend_request.status = target_status
            if parsed.reference and not spend_request.paypal_reference:
                spend_request.paypal_reference = parsed.reference
            if parsed.provider_status:
                spend_request.paypal_status = parsed.provider_status
            if spend_request.executed_at is None and target_status in TERMINAL_STATUSES:
                spend_request.executed_at = now
            spend_request.save(
                update_fields=[
                    "status",
                    "paypal_reference",
                    "paypal_status",
                    "executed_at",
                    "updated_at",
                ]
            )
            AuditEvent.record(
                OUTCOME_AUDIT[parsed.outcome],
                organization=spend_request.organization,
                agent=agent,
                spend_request=spend_request,
                actor_type=AuditEvent.ActorType.PAYPAL,
                actor_id=event.paypal_event_id,
                paypal_reference=spend_request.paypal_reference or "",
                paypal_status=spend_request.paypal_status,
                reason=event.event_type,
            )
            applied = True

        AuditEvent.record(
            AuditEvent.EventType.WEBHOOK_RECEIVED,
            organization=spend_request.organization,
            agent=agent,
            spend_request=spend_request,
            actor_type=AuditEvent.ActorType.PAYPAL,
            actor_id=event.paypal_event_id,
            paypal_event_type=event.event_type,
            provider_status=parsed.provider_status,
            applied=applied,
            reason=reason,
        )
        _mark_processed(event, now)
        return "applied" if applied else "ignored"


def _mark_processed(event: WebhookEvent, now) -> None:
    event.processed_at = now
    event.save(update_fields=["processed_at", "updated_at"])


# --- PayPal Sandbox webhook ingestion (INT-13K) ---

MAX_WEBHOOK_BODY_BYTES = 32 * 1024


class WebhookIngestionError(Exception):
    """Base class for webhook ingestion failures."""


class WebhookDisabled(WebhookIngestionError):
    """Webhook verification is not configured."""


class WebhookPayloadTooLarge(WebhookIngestionError):
    """The request body exceeds the allowed size."""


class WebhookPayloadError(WebhookIngestionError):
    """The request body is not valid JSON."""


class WebhookMissingHeaders(WebhookIngestionError):
    """Required PayPal transmission headers are missing."""


class WebhookMissingEventId(WebhookIngestionError):
    """The webhook event has no provider event id."""


class WebhookVerificationError(WebhookIngestionError):
    """PayPal did not verify the webhook signature."""


class WebhookTransportError(WebhookVerificationError):
    """PayPal verification could not be completed due to transport failure."""


class WebhookStorageError(WebhookIngestionError):
    """The webhook event could not be durably stored."""


_REQUIRED_HEADERS = (
    "PAYPAL-TRANSMISSION-ID",
    "PAYPAL-TRANSMISSION-TIME",
    "PAYPAL-TRANSMISSION-SIG",
    "PAYPAL-CERT-URL",
    "PAYPAL-AUTH-ALGO",
)


def _require_webhook_enabled(django_settings):
    try:
        config = get_paypal_config(django_settings)
    except PayPalConfigError as exc:
        raise WebhookDisabled(str(exc)) from exc
    if not (config.client_id and config.client_secret and config.webhook_id):
        raise WebhookDisabled("PayPal webhooks are not configured.")
    return config


def ingest_paypal_webhook(*, body, headers, django_settings):
    """Verify and durably store one PayPal webhook event.

    Returns ``"created"`` or ``"duplicate"``.
    """
    config = _require_webhook_enabled(django_settings)

    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise WebhookPayloadTooLarge("Webhook payload too large.")

    header_values = {}
    for header_name in _REQUIRED_HEADERS:
        value = headers.get(header_name)
        if not value:
            raise WebhookMissingHeaders(f"Missing {header_name}.")
        header_values[header_name] = value

    try:
        event = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebhookPayloadError("Invalid JSON payload.") from exc
    if not isinstance(event, dict):
        raise WebhookPayloadError("Webhook payload must be a JSON object.")

    event_id = event.get("id")
    if not event_id:
        raise WebhookMissingEventId("Webhook event is missing an id.")
    event_type = event.get("event_type") or ""

    verification_payload = {
        "transmission_id": header_values["PAYPAL-TRANSMISSION-ID"],
        "transmission_time": header_values["PAYPAL-TRANSMISSION-TIME"],
        "cert_url": header_values["PAYPAL-CERT-URL"],
        "auth_algo": header_values["PAYPAL-AUTH-ALGO"],
        "transmission_sig": header_values["PAYPAL-TRANSMISSION-SIG"],
        "webhook_id": config.webhook_id,
        "webhook_event": event,
    }

    client = PayPalClient.from_settings(django_settings)
    try:
        response = client.post(
            "/v1/notifications/verify-webhook-signature",
            json=verification_payload,
        )
    except (PayPalTransportError, PayPalTimeoutError) as exc:
        raise WebhookTransportError(str(exc)) from exc
    except (PayPalClientError, PayPalAPIError) as exc:
        raise WebhookVerificationError(str(exc)) from exc

    status_code = getattr(response, "status_code", 200) or 200
    if status_code in (401, 403):
        raise WebhookVerificationError(
            f"PayPal verification authorization failed (HTTP {status_code})."
        )
    if status_code == 429 or status_code >= 500:
        raise WebhookTransportError(
            f"PayPal verification unavailable (HTTP {status_code})."
        )
    if status_code >= 400:
        raise WebhookVerificationError(
            f"PayPal verification returned HTTP {status_code}."
        )
    try:
        verification_status = response.json().get("verification_status")
    except Exception as exc:
        raise WebhookTransportError("Invalid verification response.") from exc
    if verification_status == "FAILURE":
        raise WebhookVerificationError("Webhook signature verification failed.")
    if verification_status != "SUCCESS":
        raise WebhookTransportError("Unknown verification response.")

    try:
        with transaction.atomic():
            WebhookEvent.objects.create(
                paypal_event_id=str(event_id),
                event_type=str(event_type),
                payload=event,
                signature_verified=True,
            )
    except IntegrityError:
        return "duplicate"
    except DatabaseError as exc:
        raise WebhookStorageError(str(exc)) from exc

    return "created"


def process_webhook_event(*args, **kwargs):
    from apps.payments.webhook_processing import process_webhook_event as _impl

    return _impl(*args, **kwargs)


def process_paypal_webhook(*args, **kwargs):
    from apps.payments.webhook_processing import process_paypal_webhook as _impl

    return _impl(*args, **kwargs)


def process_webhook_events(*args, **kwargs):
    from apps.payments.webhook_processing import process_webhook_events as _impl

    return _impl(*args, **kwargs)
