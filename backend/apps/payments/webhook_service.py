"""Verified PayPal Sandbox webhook ingestion (INT-13K).

This module only authenticates and durably stores incoming webhook events.
It does not mutate payout, checkout, or spend state.
"""

import json

from django.db import DatabaseError, IntegrityError, transaction

from apps.payments.models import WebhookEvent
from apps.payments.paypal.client import (
    PayPalClient,
    PayPalClientError,
    PayPalTransportError,
)
from apps.payments.paypal.config import PayPalConfigError, get_paypal_config

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
    except PayPalTransportError as exc:
        raise WebhookTransportError(str(exc)) from exc
    except PayPalClientError as exc:
        raise WebhookVerificationError(str(exc)) from exc

    status_code = getattr(response, "status_code", 200) or 200
    if status_code >= 400:
        raise WebhookVerificationError(
            f"PayPal verification returned HTTP {status_code}."
        )
    try:
        verification_status = response.json().get("verification_status")
    except Exception as exc:
        raise WebhookVerificationError("Invalid verification response.") from exc
    if verification_status != "SUCCESS":
        raise WebhookVerificationError("Webhook signature verification failed.")

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
