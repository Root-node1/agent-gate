"""PayPal webhook ingestion. Every event is verified before it is stored."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.common.errors import ErrorCode, ensure_request_id, error_payload

from .dispatch import schedule_webhook_processing
from .executors import build_paypal_client
from .models import WebhookEvent
from .paypal import (
    PayPalAmbiguousResponse,
    PayPalAuthenticationError,
    PayPalConfigurationError,
    PayPalResponseError,
    PayPalTimeoutError,
    PayPalTransientError,
    read_signature,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)

MAX_WEBHOOK_BYTES = 1024 * 1024


def _error(request, status: int, code: ErrorCode, message: str) -> JsonResponse:
    """Return a provider-facing failure in the shared API error envelope."""
    response = JsonResponse(
        error_payload(request, code=code, message=message), status=status
    )
    response["X-Request-Id"] = ensure_request_id(request)
    return response


@csrf_exempt
@require_POST
def paypal_webhook(request):
    """Verify, store, and enqueue one PayPal event."""
    try:
        raw_body = request.body
    except RequestDataTooBig:
        return _error(
            request, 400, ErrorCode.REQUEST_TOO_LARGE, "The request body is too large."
        )
    if len(raw_body) > MAX_WEBHOOK_BYTES:
        return _error(
            request, 400, ErrorCode.REQUEST_TOO_LARGE, "The request body is too large."
        )

    content_type = (request.content_type or "").split(";")[0].strip().lower()
    if content_type != "application/json":
        return _error(
            request,
            400,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "Expected an application/json body.",
        )

    try:
        event = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error(
            request, 400, ErrorCode.INVALID_JSON, "The request body is not valid JSON."
        )
    if not isinstance(event, dict):
        return _error(
            request,
            400,
            ErrorCode.VALIDATION_ERROR,
            "The webhook event must be a JSON object.",
        )

    event_id = event.get("id")
    event_type = event.get("event_type")
    if not isinstance(event_id, str) or not event_id.strip():
        return _error(
            request,
            400,
            ErrorCode.VALIDATION_ERROR,
            "The webhook event is missing an id.",
        )
    if not isinstance(event_type, str) or not event_type.strip():
        return _error(
            request,
            400,
            ErrorCode.VALIDATION_ERROR,
            "The webhook event is missing a type.",
        )
    if len(event_id) > 100 or len(event_type) > 100:
        return _error(
            request,
            400,
            ErrorCode.VALIDATION_ERROR,
            "The webhook event fields are too long.",
        )

    signature = read_signature(request.headers)
    if signature is None:
        return _error(
            request,
            400,
            ErrorCode.VALIDATION_ERROR,
            "The webhook signature headers are missing.",
        )

    webhook_id = getattr(settings, "PAYPAL_WEBHOOK_ID", "")
    if not webhook_id:
        logger.error("PayPal webhook received without PAYPAL_WEBHOOK_ID set.")
        return _error(
            request,
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Webhook verification is not configured.",
        )

    try:
        client = build_paypal_client()
    except PayPalConfigurationError:
        logger.exception("PayPal webhook client configuration is invalid.")
        return _error(
            request,
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Webhook verification is not configured.",
        )

    try:
        verified = verify_webhook_signature(client, webhook_id, signature, event)
    except PayPalResponseError as exc:
        if exc.status_code in {401, 403}:
            logger.warning("PayPal webhook verification was not authorized.")
            return _error(
                request,
                503,
                ErrorCode.SERVICE_UNAVAILABLE,
                "Webhook verification is unavailable.",
            )
        verified = False
    except (
        PayPalAuthenticationError,
        PayPalConfigurationError,
        PayPalTimeoutError,
        PayPalTransientError,
        PayPalAmbiguousResponse,
    ):
        logger.warning("PayPal webhook verification could not complete.")
        return _error(
            request,
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            "Webhook verification is unavailable.",
        )
    finally:
        client.close()

    if not verified:
        return _error(
            request,
            400,
            ErrorCode.VALIDATION_ERROR,
            "The webhook signature could not be verified.",
        )

    with transaction.atomic():
        record, created = WebhookEvent.objects.get_or_create(
            paypal_event_id=event_id,
            defaults={
                "event_type": event_type,
                "payload": event,
                "signature_verified": True,
            },
        )
        if not created and record.processed_at is None:
            record.event_type = event_type
            record.payload = event
            record.signature_verified = True
            record.save(
                update_fields=[
                    "event_type",
                    "payload",
                    "signature_verified",
                    "updated_at",
                ]
            )

    if created or record.processed_at is None:
        schedule_webhook_processing(record.pk)

    return JsonResponse({"status": "ok"})
