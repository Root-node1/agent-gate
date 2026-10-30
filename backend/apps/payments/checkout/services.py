"""Checkout order creation against the PayPal Orders v2 API (INT-13G).

Public API:
- :func:`create_checkout_order` — atomically reserves a local CheckoutOrder,
  then calls PayPal ``POST /v2/checkout/orders`` with CAPTURE intent.
- :func:`get_paypal_order` — read-only ``GET /v2/checkout/orders/{id}``
  for reconciliation of uncertain outcomes.
- :func:`build_order_payload` / :func:`extract_approval_url` — pure helpers
  that are independently testable without PayPal or a database.

All external HTTP goes through :class:`PayPalClient`; this module never
duplicates OAuth logic, never follows redirects, and never auto-retries
financial POSTs.
"""

import logging
import uuid

from django.db import IntegrityError, transaction

from apps.common.money import to_major
from apps.payments.models import CheckoutOrder
from apps.payments.paypal.client import (
    PayPalAPIError,
    PayPalClient,
    PayPalUncertainOutcomeError,
)

logger = logging.getLogger(__name__)

_ORDER_PATH = "/v2/checkout/orders"


class CheckoutOperationConflict(Exception):
    """Idempotency key was reused with a different amount or currency."""


def _format_amount(amount_minor: int, currency: str) -> str:
    """Format a minor-unit integer as a PayPal-compatible major-unit string.

    PayPal expects ``value`` as a string with the correct number of decimal
    places for the currency (e.g. ``"10.00"`` for USD, ``"1000"`` for JPY).
    """
    return str(to_major(amount_minor, currency))


def build_order_payload(
    amount_minor: int,
    currency: str,
) -> dict:
    """Build the Orders v2 request body for a CAPTURE-intent checkout.

    The amount originates from the immutable ``CheckoutOrder`` model fields;
    this function is called with values already read from the model, so the
    client can never override the stored financial snapshot.
    """
    return {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": currency,
                    "value": _format_amount(amount_minor, currency),
                }
            }
        ],
    }


def extract_approval_url(paypal_response: dict) -> str | None:
    """Extract the payer-approval URL from PayPal's HATEOAS links.

    PayPal may return ``rel: "approve"`` (standard checkout) or
    ``rel: "payer-action"`` (PayPal Wallet with experience context).
    Only links with ``method: "GET"`` are considered.
    """
    for link in paypal_response.get("links", []):
        if (
            link.get("rel") in ("approve", "payer-action")
            and link.get("method") == "GET"
        ):
            href = link.get("href")
            if href:
                return href
    return None


def create_checkout_order(
    organization,
    *,
    amount_minor: int,
    currency: str,
    idempotency_key: uuid.UUID,
    client: PayPalClient,
) -> tuple[CheckoutOrder, str | None, bool]:
    """Create a PayPal Sandbox checkout order.

    Atomically reserves a ``CheckoutOrder`` row keyed by
    ``idempotency_key`` before any HTTP call to PayPal, so concurrent
    requests for the same key cannot create duplicate orders.

    The PayPal ``POST`` is issued **outside** the database transaction so
    no row lock is held during the network round-trip.  The
    ``PayPal-Request-Id`` header is set to the idempotency-key string,
    giving PayPal-level idempotency for reconciliation retries.

    Args:
        organization: The organization to scope the checkout order to.
        amount_minor: The order amount in minor units (e.g. cents).
        currency: The ISO 4217 currency code.
        idempotency_key: A stable UUID for retry-safe idempotency.
        client: An :class:`PayPalClient` instance (injected for testability).

    Returns:
        A tuple ``(checkout_order, approval_url, replayed)`` where:
        - ``approval_url`` is the payer-approval URL, or ``None`` when PayPal
          returned an uncertain outcome (timeout/5xx).
        - ``replayed`` is ``True`` when the local CheckoutOrder already existed
          (idempotent request served from the database without a PayPal call).

    Raises:
        CheckoutOperationConflict: when the key is reused with a different
            amount or currency.
        PayPalAPIError: when PayPal rejects the request (4xx).  The
            CheckoutOrder is transitioned to ``DECLINED`` before re-raising.
        PayPalUncertainOutcomeError: **not** propagated — caught internally.
            The CheckoutOrder stays in ``CREATED`` state and ``approval_url``
            is ``None``; the caller may retry with the same key.
    """
    currency = currency.upper()
    request_id = str(idempotency_key)

    # --- 1. Atomically reserve the local operation ---------------------------
    try:
        with transaction.atomic():
            checkout = CheckoutOrder.objects.create(
                organization=organization,
                amount_minor=amount_minor,
                currency=currency,
                idempotency_key=idempotency_key,
            )
    except IntegrityError:
        # Concurrent request already created a row with this key.
        checkout = CheckoutOrder.objects.get(idempotency_key=idempotency_key)
        if checkout.amount_minor != amount_minor or checkout.currency != currency:
            raise CheckoutOperationConflict(
                "Idempotency-Key was reused with a different amount or currency."
            )
        if checkout.paypal_order_id is not None:
            return checkout, checkout.payer_action_url, True
        # Existing row in CREATED state from a prior uncertain outcome —
        # fall through to retry the PayPal call (PayPal-Request-Id = key).

    # --- 2. External HTTP call — NO DB transaction held -----------------------
    try:
        response = client.post(
            _ORDER_PATH,
            json=build_order_payload(checkout.amount_minor, checkout.currency),
            request_id=request_id,
        )
    except PayPalUncertainOutcomeError:
        logger.warning(
            "Uncertain PayPal outcome for checkout order %s (key=%s); "
            "left in CREATED state for reconciliation.",
            checkout.pk,
            idempotency_key,
        )
        checkout.refresh_from_db()
        return checkout, None, False
    except PayPalAPIError:
        checkout.refresh_from_db()
        if checkout.status == CheckoutOrder.Status.CREATED:
            checkout.transition_to(CheckoutOrder.Status.DECLINED)
            checkout.save(update_fields=["status", "updated_at"])
        raise

    paypal_order_id = response.get("id")
    approval_url = extract_approval_url(response)

    if paypal_order_id is None:
        # PayPal returned 2xx without an order ID — treat as uncertain.
        checkout.refresh_from_db()
        return checkout, None, False

    # --- 3. Persist PayPal response atomically ------------------------------
    with transaction.atomic():
        checkout.refresh_from_db()
        if checkout.paypal_order_id is not None:
            # A concurrent request already persisted this order.
            return checkout, checkout.payer_action_url, True
        checkout.paypal_order_id = paypal_order_id
        checkout.payer_action_url = approval_url
        checkout.transition_to(CheckoutOrder.Status.PAYER_ACTION_REQUIRED)
        checkout.save(
            update_fields=[
                "paypal_order_id",
                "payer_action_url",
                "status",
                "updated_at",
            ]
        )

    return checkout, approval_url, False


def get_paypal_order(
    *, checkout_order: CheckoutOrder, client: PayPalClient
) -> dict | None:
    """Fetch PayPal order details for reconciliation (GET).

    Uses ``GET /v2/checkout/orders/{id}`` — a safe, retryable operation.
    Returns the parsed PayPal response dict, or ``None`` if no PayPal
    order ID has been recorded yet on the CheckoutOrder.
    """
    if checkout_order.paypal_order_id is None:
        return None
    return client.get(f"{_ORDER_PATH}/{checkout_order.paypal_order_id}")
