"""Checkout order creation against the PayPal Orders v2 API (INT-13G).

Public API:
- :func:`create_checkout_order` — atomically reserves a local CheckoutOrder,
  then calls PayPal ``POST /v2/checkout/orders`` with CAPTURE intent.
- :func:`capture_checkout_order` — explicitly captures a previously-approved
  PayPal order via ``GET`` (approval verification) then ``POST .../capture``.
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
from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.common.money import to_major
from apps.payments.models import CheckoutOrder
from apps.payments.paypal.client import (
    PayPalAPIError,
    PayPalClient,
    PayPalConnectionError,
    PayPalNotFoundError,
    PayPalServerError,
    PayPalTimeoutError,
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


# ---------------------------------------------------------------------------
# PayPal Checkout Orders v2 — explicit capture (INT-13H)
# ---------------------------------------------------------------------------

#: PayPal capture is the only intent this service handles.
_CAPTURE_INTENT = "CAPTURE"

#: PayPal order/capture statuses used to drive verification and reconciliation.
_PAYPAL_ORDER_APPROVED = "APPROVED"
_PAYPAL_ORDER_COMPLETED = "COMPLETED"
_PAYPAL_CAPTURE_COMPLETED = "COMPLETED"
_PAYPAL_CAPTURE_PENDING = "PENDING"

#: PayPal statuses that mean the capture has definitively settled (one of these
#: ends the capture lifecycle on PayPal's side).
_PAYPAL_CAPTURE_TERMINAL = frozenset(
    {"COMPLETED", "DENIED", "DECLINED", "REFUNDED", "PARTIALLY_REFUNDED"}
)


class CaptureOutcome:
    """Possible outcomes of a capture attempt (not DB statuses)."""

    COMPLETED = "completed"
    PENDING = "pending"


class CaptureError(Exception):
    """Base class for capture workflow failures raised to the view layer."""


class CaptureConflict(CaptureError):
    """A different capture operation already owns this checkout order."""


class CaptureNotApproved(CaptureError):
    """The checkout order (or its PayPal order) is not in an approvable state."""


class CaptureVerificationError(CaptureError):
    """A PayPal response did not match the immutable local financial snapshot,
    or PayPal definitively rejected the capture."""


def _capture_path(paypal_order_id: str) -> str:
    return f"{_ORDER_PATH}/{paypal_order_id}/capture"


def _purchase_unit_amount(paypal_order: dict) -> dict | None:
    units = paypal_order.get("purchase_units") or []
    if not units:
        return None
    return units[0].get("amount")


def _verify_paypal_order(paypal_order: dict, checkout: CheckoutOrder) -> str:
    """Verify PayPal order identity, intent, and amount against the local snapshot.

    Raises :class:`CaptureVerificationError` on any mismatch.  Returns the
    PayPal order ``status`` on success so the caller can reconcile or proceed.
    """
    if paypal_order.get("id") != checkout.paypal_order_id:
        raise CaptureVerificationError(
            "PayPal order id does not match the local checkout record."
        )
    intent = paypal_order.get("intent")
    if intent != _CAPTURE_INTENT:
        raise CaptureVerificationError(
            f"PayPal order intent is {intent!r}, expected {_CAPTURE_INTENT!r}."
        )
    amount = _purchase_unit_amount(paypal_order)
    if amount is None:
        raise CaptureVerificationError("PayPal order has no purchase-unit amount.")
    _verify_amount(amount, checkout)
    return paypal_order.get("status", "")


def _verify_amount(amount: dict, checkout: CheckoutOrder) -> None:
    """Compare a PayPal amount object to the immutable local financial snapshot."""
    currency = amount.get("currency_code")
    if currency != checkout.currency:
        raise CaptureVerificationError(
            f"Currency mismatch: PayPal returned {currency!r}, "
            f"local is {checkout.currency!r}."
        )
    value = amount.get("value")
    if not value:
        raise CaptureVerificationError("PayPal amount has no value.")
    try:
        remote = Decimal(value)
    except (TypeError, ValueError) as exc:
        raise CaptureVerificationError("PayPal amount value is not numeric.") from exc
    local = to_major(checkout.amount_minor, checkout.currency)
    if remote != local:
        raise CaptureVerificationError(
            f"Amount mismatch: PayPal returned {value!r} {currency!r}, "
            f"local is {local} {checkout.currency!r}."
        )


def _extract_capture(paypal_order: dict) -> dict | None:
    """Extract the first capture object from a PayPal order response."""
    units = paypal_order.get("purchase_units") or []
    if not units:
        return None
    payments = units[0].get("payments") or {}
    captures = payments.get("captures") or []
    if not captures:
        return None
    return captures[0]


def _verify_capture(capture: dict | None, checkout: CheckoutOrder) -> str:
    """Validate a capture object exists and matches the local snapshot.

    Does not distinguish success from pending/terminal here — that is the
    caller's concern.  Raises :class:`CaptureVerificationError` (a terminal,
    justified failure) when the capture identity, id, or amount is missing or
    mismatched.  Returns the capture ``status``.
    """
    if capture is None:
        raise CaptureVerificationError(
            "PayPal capture response contained no capture object."
        )
    capture_id = capture.get("id")
    if not capture_id:
        raise CaptureVerificationError("PayPal capture has no id.")
    amount = capture.get("amount") or {}
    _verify_amount(amount, checkout)
    return capture.get("status", "")


def _decline(checkout: "CheckoutOrder", reason: str) -> None:
    """Transition a pending capture to a justified DECLINED terminal state.

    Only acts when the order is still ``CAPTURE_PENDING`` (guarded against a
    concurrent capture that already resolved to COMPLETED).  Records a single
    ``payment.failed`` audit event.
    """
    with transaction.atomic():
        checkout.refresh_from_db()
        if checkout.status != CheckoutOrder.Status.CAPTURE_PENDING:
            return
        checkout.transition_to(CheckoutOrder.Status.DECLINED)
        checkout.save(update_fields=["status", "updated_at"])
        AuditEvent.record(
            AuditEvent.EventType.PAYMENT_FAILED,
            organization=checkout.organization,
            actor_type=AuditEvent.ActorType.PAYPAL,
            failure_reason=reason,
            paypal_order_id=checkout.paypal_order_id,
        )


def _commit_completed(checkout: "CheckoutOrder", capture: dict) -> bool:
    """Persist a confirmed capture, idempotently.

    Returns ``True`` when the order was already COMPLETED by a concurrent
    caller (a safe replay), ``False`` when this call performed the transition.
    """
    capture_id = capture.get("id")
    with transaction.atomic():
        checkout.refresh_from_db()
        if checkout.status == CheckoutOrder.Status.COMPLETED:
            return True
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
    return False


def capture_checkout_order(
    *,
    checkout_order: "CheckoutOrder",
    organization_id: "uuid.UUID",
    capture_idempotency_key: "uuid.UUID",
    client: "PayPalClient",
) -> tuple["CheckoutOrder", str, bool]:
    """Explicitly capture a previously-approved PayPal checkout order.

    The capture is driven by the caller-supplied ``capture_idempotency_key``,
    which is forwarded to PayPal as the stable ``PayPal-Request-Id`` header and
    persisted on the ``CheckoutOrder`` as the durable operation identity.  The
    same key must be reused for any retry so the operation resolves to the same
    row.

    Phases (no external HTTP happens inside a database transaction):

    1. **Reserve** — under ``SELECT ... FOR UPDATE``, atomically assign the
       capture key and move ``APPROVED -> CAPTURE_PENDING``.  A concurrent
       *different* key is rejected; the same key re-enters to reconcile.
    2. **Verify approval (GET)** — confirm PayPal reports the order as
       ``APPROVED`` (or already ``COMPLETED``), the ``CAPTURE`` intent, and an
       order id / amount / currency that match the immutable local snapshot.
    3. **Capture (POST)** — ``POST /v2/checkout/orders/{id}/capture`` with the
       stable idempotency key.  PayPal dedups by ``PayPal-Request-Id``.
    4. **Persist** — validate the capture (``COMPLETED``, id, amount) and move
       ``CAPTURE_PENDING -> COMPLETED``; record ``payment.succeeded``.

    Returns ``(checkout, outcome, replayed)`` where ``outcome`` is
    :attr:`CaptureOutcome.COMPLETED` or :attr:`CaptureOutcome.PENDING` and
    ``replayed`` indicates an idempotent replay rather than a fresh capture.

    Raises:
        CaptureConflict: a different capture operation owns this order.
        CaptureNotApproved: the order (or its PayPal record) is not approved.
        CaptureVerificationError: PayPal data mismatched the local snapshot,
            or PayPal definitively rejected the capture (404 / terminal status).
        PayPalAPIError: PayPal rejected an attempt (4xx).  The order is moved
            to ``DECLINED`` before re-raising so the view can return 502.
    """
    request_id = str(capture_idempotency_key)

    # --- 1. Atomically reserve the capture operation -------------------------
    with transaction.atomic():
        checkout = CheckoutOrder.objects.select_for_update().get(pk=checkout_order.pk)
        if checkout.organization_id != organization_id:
            raise CaptureConflict("Checkout order belongs to a different organization.")
        if checkout.paypal_order_id is None:
            raise CaptureVerificationError(
                "Checkout order has no PayPal order id; cannot capture."
            )

        if checkout.status == CheckoutOrder.Status.COMPLETED:
            return checkout, CaptureOutcome.COMPLETED, True

        current_key = checkout.capture_idempotency_key
        if current_key == capture_idempotency_key:
            # Same key already in progress (e.g. an uncertain prior attempt):
            # fall through to reconciliation after releasing the lock.
            pass
        elif current_key is not None:
            raise CaptureConflict(
                "A capture operation is already in progress for this checkout order."
            )
        elif checkout.status == CheckoutOrder.Status.APPROVED:
            checkout.capture_idempotency_key = capture_idempotency_key
            checkout.transition_to(CheckoutOrder.Status.CAPTURE_PENDING)
            checkout.save(
                update_fields=["capture_idempotency_key", "status", "updated_at"]
            )
        else:
            raise CaptureNotApproved(
                f"Checkout order is not approved (status={checkout.status!r})."
            )
    # Lock released here — no external HTTP is performed under the lock.

    # --- 2. Verify PayPal approval server-side (safe GET) -------------------
    try:
        paypal_order = client.get(f"{_ORDER_PATH}/{checkout.paypal_order_id}")
    except (
        PayPalTimeoutError,
        PayPalConnectionError,
        PayPalServerError,
        PayPalUncertainOutcomeError,
    ):
        # Uncertain — preserve CAPTURE_PENDING and let the caller reconcile later.
        checkout.refresh_from_db()
        return checkout, CaptureOutcome.PENDING, False
    except PayPalNotFoundError:
        checkout.refresh_from_db()
        _decline(checkout, "paypal_order_not_found")
        raise CaptureVerificationError("Referenced PayPal order was not found.")
    except PayPalAPIError:
        # Auth/protocol errors during verification: leave pending for a config fix.
        checkout.refresh_from_db()
        raise

    try:
        paypal_status = _verify_paypal_order(paypal_order, checkout)
    except CaptureVerificationError:
        _decline(checkout, "paypal_order_verification_failed")
        raise

    # Reconcile: PayPal may already report the order COMPLETED (the capture
    # succeeded on a prior attempt whose HTTP outcome was uncertain).
    if paypal_status == _PAYPAL_ORDER_COMPLETED:
        capture = _extract_capture(paypal_order)
        try:
            cap_status = _verify_capture(capture, checkout)
        except CaptureVerificationError:
            _decline(checkout, "reconcile_capture_verification_failed")
            raise
        if cap_status != _PAYPAL_CAPTURE_COMPLETED:
            checkout.refresh_from_db()
            _decline(checkout, f"paypal_capture_status_{cap_status}")
            raise CaptureVerificationError(
                f"PayPal capture status is {cap_status!r}, expected COMPLETED."
            )
        replayed = _commit_completed(checkout, capture)
        return checkout, CaptureOutcome.COMPLETED, replayed

    if paypal_status != _PAYPAL_ORDER_APPROVED:
        checkout.refresh_from_db()
        _decline(checkout, f"paypal_order_status_{paypal_status}")
        if paypal_status == "":
            raise CaptureNotApproved("PayPal order is not yet approved.")
        raise CaptureNotApproved(
            f"PayPal order is not approved (status={paypal_status!r})."
        )

    # --- 3. POST the capture (idempotent via PayPal-Request-Id) --------------
    try:
        response = client.post(
            _capture_path(checkout.paypal_order_id), request_id=request_id
        )
    except PayPalUncertainOutcomeError:
        # Timeout / connection loss / 5xx: the capture may have succeeded.
        # Preserve CAPTURE_PENDING and the stable key for reconciliation.
        checkout.refresh_from_db()
        return checkout, CaptureOutcome.PENDING, False
    except PayPalAPIError:
        # PayPal definitively rejected the capture (4xx).
        checkout.refresh_from_db()
        _decline(checkout, "paypal_capture_rejected")
        raise

    # --- 4. Validate the capture and persist ---------------------------------
    capture = _extract_capture(response)
    try:
        cap_status = _verify_capture(capture, checkout)
    except CaptureVerificationError:
        _decline(checkout, "capture_response_verification_failed")
        raise
    if cap_status == _PAYPAL_CAPTURE_PENDING:
        # The capture was created but PayPal reports it as still pending.
        checkout.refresh_from_db()
        return checkout, CaptureOutcome.PENDING, False
    if cap_status != _PAYPAL_CAPTURE_COMPLETED:
        checkout.refresh_from_db()
        _decline(checkout, f"paypal_capture_status_{cap_status}")
        raise CaptureVerificationError(
            f"PayPal capture status is {cap_status!r}, expected COMPLETED."
        )
    replayed = _commit_completed(checkout, capture)
    return checkout, CaptureOutcome.COMPLETED, replayed
