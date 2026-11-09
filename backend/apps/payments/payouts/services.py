"""Payout reservation and submission services (INT-13I / INT-13J).

Public API:
- :func:`reserve_payout` — atomically validates eligibility and creates a
  durable :class:`~apps.payments.payouts.models.PayoutReservation` for an
  approved SpendRequest.  Reservation does NOT transfer money and makes NO
  PayPal API call.
- :func:`submit_payout` — submits an existing reservation to PayPal Payouts
  v1 sandbox.  Durable submission state is committed before any HTTP call;
  uncertain outcomes leave the reservation pending for reconciliation.
- :func:`reconcile_payout` — queries PayPal batch/item status for a pending
  submission and advances the reservation to an authoritative state.

SpendRequest lifecycle invariant (INT-13J.2):
  PayoutReservation is the authoritative payout lifecycle.  SpendRequest stays
  APPROVED after reservation, submission, and completion so approved spending
  remains counted in BUDGET_STATUSES without a broader state-machine redesign.
  Payment execution evidence is recorded on PayoutReservation and AuditEvent.

All financial and recipient values are immutable snapshots taken from the
SpendRequest at reservation time.
"""

import uuid
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

import engine
from apps.accounts.models import Organization
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.common.money import to_major
from apps.payees.models import DestinationType, Payee
from apps.payments.paypal.client import (
    PayPalAPIError,
    PayPalClient,
    PayPalClientError,
    PayPalConflictError,
    PayPalRateLimitError,
    PayPalTransportError,
    PayPalUncertainOutcomeError,
)
from apps.payments.paypal.config import PayPalConfigError, get_paypal_config
from apps.policies.models import Policy
from apps.spend import services as spend_services
from apps.spend.models import SpendRequest

from .models import PayoutReservation


class PayoutReservationError(Exception):
    """Base class for payout reservation failures."""


class PayoutNotEligible(PayoutReservationError):
    """The SpendRequest is not eligible for payout reservation."""


class PayoutAlreadyReserved(PayoutReservationError):
    """A payout reservation already exists for this SpendRequest."""


class PayoutFeatureDisabled(PayoutReservationError):
    """PayPal Payouts is not enabled or not configured."""


class PayoutSubmissionError(PayoutReservationError):
    """Base class for payout submission failures."""


class PayoutNotReserved(PayoutSubmissionError):
    """The reservation does not exist or is not in a submittable state."""


class PayoutAlreadySubmitted(PayoutSubmissionError):
    """The reservation has already been submitted to PayPal."""


@dataclass(frozen=True)
class SubmissionResult:
    """Outcome of a payout submission or reconciliation attempt."""

    reservation: PayoutReservation
    outcome: str  # "submitted", "pending", "failed", "uncertain", "already_submitted", "reconciled"
    paypal_batch_id: str | None = None
    paypal_item_id: str | None = None
    batch_status: str | None = None
    error: str | None = None


def _require_payouts_enabled(django_settings) -> None:
    """Ensure PayPal Payouts is enabled with valid sandbox credentials."""
    try:
        config = get_paypal_config(django_settings)
    except PayPalConfigError as exc:
        raise PayoutFeatureDisabled(str(exc)) from exc
    if not config.payouts_enabled:
        raise PayoutFeatureDisabled("Payouts is not enabled.")


def _recheck_budget_and_limits(
    spend_request: SpendRequest, agent, policy: Policy, now
) -> list[str] | None:
    """Return rule ids that now deny the spend, or None when still permitted.

    Mirrors the approval recheck in ``apps.approvals.services._recheck_failure``
    so a reservation is never made for a spend that current policy or budgets
    would reject.
    """
    from apps.agents.models import Agent

    if spend_request.destination_fingerprint:
        payee = (
            Payee.objects.filter(
                organization_id=spend_request.organization_id,
                merchant_ref=spend_request.merchant_ref,
            )
            .only("destination_fingerprint")
            .first()
        )
        if (
            payee
            and payee.destination_fingerprint != spend_request.destination_fingerprint
        ):
            return ["destination_changed"]

    decision = engine.evaluate(
        engine.SpendInput(
            amount=to_major(spend_request.amount_minor, spend_request.currency),
            currency=spend_request.currency,
            merchant=spend_request.merchant_ref,
            source=spend_services.rule_source(spend_request.source_type),
            purpose=spend_request.purpose,
            evidence_excerpt=spend_request.evidence_excerpt,
            agent_active=agent.status == Agent.Status.ACTIVE,
        ),
        spend_services.build_limits(policy),
        spend_services.build_spent(
            agent, policy, spend_request.currency, spend_request.merchant_ref, now
        ),
    )
    if decision.outcome == engine.DENY:
        return decision.matched_rules
    return None


@transaction.atomic
def reserve_payout(
    organization: Organization,
    *,
    spend_request_id,
    idempotency_key,
    django_settings,
):
    """Atomically reserve a payout for an approved SpendRequest.

    Returns ``(reservation, replayed)`` where ``replayed`` is ``True`` when an
    existing reservation for the same idempotency key was returned without
    creating a new row.

    Raises:
        PayoutFeatureDisabled: PayPal Payouts is not enabled or misconfigured.
        PayoutNotEligible: the SpendRequest is not eligible for reservation.
        PayoutAlreadyReserved: a reservation already exists for this key/request.
    """
    _require_payouts_enabled(django_settings)

    # --- 1. Lock and load the SpendRequest --------------------------------
    try:
        spend_request = (
            SpendRequest.objects.select_for_update(of=("self",))
            .select_related("approval")
            .get(pk=spend_request_id, organization=organization)
        )
    except SpendRequest.DoesNotExist:
        raise PayoutNotEligible("SpendRequest not found or not in this organization.")

    # --- 2. Status must be APPROVED ---------------------------------------
    if spend_request.status != SpendRequest.Status.APPROVED:
        raise PayoutNotEligible(
            f"SpendRequest is not approved (status={spend_request.status!r})."
        )

    # --- 3. Linked approval (when required) must be APPROVED and live -----
    approval = getattr(spend_request, "approval", None)
    if approval is not None:
        now = timezone.now()
        if approval.outcome != Approval.Outcome.APPROVED:
            raise PayoutNotEligible(
                f"Linked approval is not approved (outcome={approval.outcome!r})."
            )
        if approval.expires_at <= now:
            raise PayoutNotEligible("Linked approval has expired.")

    # --- 4. Active same-organization Payee with PAYPAL_EMAIL destination ---
    try:
        payee = Payee.objects.get(
            organization=organization,
            merchant_ref=spend_request.merchant_ref,
        )
    except Payee.DoesNotExist:
        raise PayoutNotEligible(
            "No active Payee for this merchant in this organization."
        )
    if payee.status != Payee.Status.ACTIVE:
        raise PayoutNotEligible("Payee is not active.")
    if spend_request.destination_type != DestinationType.PAYPAL_EMAIL:
        raise PayoutNotEligible("Only PAYPAL_EMAIL destinations are supported for V1.")
    if (
        spend_request.destination_fingerprint
        and spend_request.destination_fingerprint != payee.destination_fingerprint
    ):
        raise PayoutNotEligible(
            "Payee destination fingerprint does not match the SpendRequest."
        )

    # --- 5. Budget and spend-limit recheck --------------------------------
    agent = spend_request.agent
    policy = spend_services.current_policy(agent, for_update=True)
    if policy is None:
        raise PayoutNotEligible("This agent has no current policy.")
    now = timezone.now()
    failed_rules = _recheck_budget_and_limits(spend_request, agent, policy, now)
    if failed_rules:
        raise PayoutNotEligible(
            "Current policy or budget no longer permits this spend."
        )

    # --- 6. Idempotency: return existing reservation for same key ----------
    existing = PayoutReservation.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        if existing.spend_request_id != spend_request_id:
            raise PayoutAlreadyReserved(
                "Idempotency-Key was reused with a different SpendRequest."
            )
        return existing, True

    # --- 7. One active reservation per SpendRequest ------------------------
    if PayoutReservation.objects.filter(spend_request=spend_request).exists():
        raise PayoutAlreadyReserved(
            "A payout reservation already exists for this SpendRequest."
        )

    # --- 8. Create the immutable reservation ------------------------------
    now = timezone.now()
    reservation = PayoutReservation.objects.create(
        organization=organization,
        spend_request=spend_request,
        payee=payee,
        amount_minor=spend_request.amount_minor,
        currency=spend_request.currency,
        destination_type=spend_request.destination_type,
        destination_value=spend_request.destination_value,
        destination_fingerprint=spend_request.destination_fingerprint,
        idempotency_key=idempotency_key,
        status=PayoutReservation.Status.RESERVED,
    )

    # --- 9. Audit the reservation -----------------------------------------
    AuditEvent.record(
        AuditEvent.EventType.PAYMENT_RESERVED,
        organization=organization,
        agent=agent,
        spend_request=spend_request,
        actor_type=AuditEvent.ActorType.USER,
        actor_id="",
        amount=to_major(reservation.amount_minor, reservation.currency),
        currency=reservation.currency,
        merchant=spend_request.merchant_ref,
        destination_type=reservation.destination_type,
        destination_fingerprint=reservation.destination_fingerprint,
        payout_reservation_id=str(reservation.id),
    )

    return reservation, False


def _validate_submission_eligibility(reservation: PayoutReservation, now):
    """Re-validate that a RESERVED reservation can still be submitted.

    Returns (spend_request, agent, policy, payee) or raises PayoutNotReserved.
    """
    spend_request = reservation.spend_request
    if spend_request.status != SpendRequest.Status.APPROVED:
        raise PayoutNotReserved(
            f"SpendRequest is no longer approved (status={spend_request.status!r})."
        )

    approval = getattr(spend_request, "approval", None)
    if approval is not None:
        if approval.outcome != Approval.Outcome.APPROVED:
            raise PayoutNotReserved(
                f"Linked approval is not approved (outcome={approval.outcome!r})."
            )
        if approval.expires_at <= now:
            raise PayoutNotReserved("Linked approval has expired.")

    try:
        payee = Payee.objects.get(
            organization=reservation.organization,
            merchant_ref=spend_request.merchant_ref,
        )
    except Payee.DoesNotExist:
        raise PayoutNotReserved(
            "No active Payee for this merchant in this organization."
        )
    if payee.status != Payee.Status.ACTIVE:
        raise PayoutNotReserved("Payee is not active.")
    if spend_request.destination_type != DestinationType.PAYPAL_EMAIL:
        raise PayoutNotReserved("Only PAYPAL_EMAIL destinations are supported for V1.")
    if (
        spend_request.destination_fingerprint
        and spend_request.destination_fingerprint != payee.destination_fingerprint
    ):
        raise PayoutNotReserved(
            "Payee destination fingerprint does not match the SpendRequest."
        )

    agent = spend_request.agent
    policy = spend_services.current_policy(agent, for_update=True)
    if policy is None:
        raise PayoutNotReserved("This agent has no current policy.")
    failed_rules = _recheck_budget_and_limits(spend_request, agent, policy, now)
    if failed_rules:
        raise PayoutNotReserved(
            "Current policy or budget no longer permits this spend."
        )

    return spend_request, agent, policy, payee


def _build_payout_payload(reservation: PayoutReservation, sender_batch_id) -> dict:
    """Build the PayPal Payouts v1 request body from immutable snapshots."""
    amount_major = to_major(reservation.amount_minor, reservation.currency)
    return {
        "sender_batch_header": {
            "sender_batch_id": str(sender_batch_id),
            "email_subject": "Your payout from AgentGate",
            "email_message": "You have received a payout.",
            "recipient_type": "EMAIL",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "receiver": reservation.destination_value,
                "amount": {
                    "value": str(amount_major),
                    "currency": reservation.currency,
                },
                "note": "AgentGate payout",
                "sender_item_id": str(reservation.id),
            }
        ],
    }


def _parse_payout_response(body: dict) -> tuple[str, str, str]:
    """Extract batch_id, item_id, and batch_status from PayPal response."""
    batch_header = body.get("batch_header", {}) or {}
    batch_id = batch_header.get("payout_batch_id")
    batch_status = batch_header.get("batch_status")
    items = body.get("items", []) or []
    item_id = None
    if items:
        item_id = items[0].get("payout_item_id")
    return batch_id, item_id, batch_status


@transaction.atomic
def _transition_to_submission_pending(reservation: PayoutReservation) -> None:
    """Persist sender_batch_id and transition to SUBMISSION_PENDING, then commit."""
    if not reservation.sender_batch_id:
        reservation.sender_batch_id = uuid.uuid4()
    reservation.status = PayoutReservation.Status.SUBMISSION_PENDING
    reservation.submission_attempted_at = timezone.now()
    reservation.submission_error = None
    reservation.save()


@transaction.atomic
def _transition_to_submitted(reservation: PayoutReservation, batch_id, item_id) -> None:
    """Store PayPal identifiers and transition to SUBMITTED."""
    reservation.paypal_payout_batch_id = batch_id
    reservation.paypal_payout_item_id = item_id
    reservation.status = PayoutReservation.Status.SUBMITTED
    reservation.submission_error = None
    reservation.save()


@transaction.atomic
def _transition_to_failed(reservation: PayoutReservation, error: str) -> None:
    """Transition to FAILED and record a sanitized error (no secrets)."""
    reservation.status = PayoutReservation.Status.FAILED
    reservation.submission_error = error[:1000]
    reservation.save()


@transaction.atomic
def _transition_to_uncertain(reservation: PayoutReservation) -> None:
    """Mark the outcome as uncertain; the reservation stays recoverable."""
    reservation.status = PayoutReservation.Status.UNCERTAIN
    reservation.save()


def _submit_to_paypal(
    reservation: PayoutReservation, django_settings, session=None
) -> tuple[str, str, str]:
    """Call PayPal Payouts v1 POST /v1/payments/payouts.

    Returns (batch_id, item_id, batch_status).  Raises
    PayPalUncertainOutcomeError on timeout/5xx, PayPalAPIError on 4xx.
    """
    client = PayPalClient.from_settings(django_settings, session=session)
    payload = _build_payout_payload(reservation, reservation.sender_batch_id)
    try:
        response = client.post(
            "/v1/payments/payouts",
            json=payload,
            request_id=str(reservation.sender_batch_id),
        )
    except PayPalTransportError as exc:
        raise PayPalUncertainOutcomeError(f"PayPal transport error: {exc}") from exc
    # PayPalClient._request raises on non-2xx in production; when mocked,
    # check status codes here to surface the same exceptions.
    status = getattr(response, "status_code", 200) or 200
    if status >= 500:
        raise PayPalUncertainOutcomeError(
            f"PayPal returned HTTP {status}; outcome uncertain."
        )
    if status == 429:
        raise PayPalUncertainOutcomeError(
            "PayPal rate-limited the request; outcome uncertain."
        )
    if status >= 400:
        body = None
        try:
            body = response.json()
        except Exception:
            body = None
        structured = isinstance(body, dict) and bool(
            body.get("name") or body.get("message") or body.get("details")
        )
        if structured:
            exc = PayPalAPIError(f"PayPal returned HTTP {status}.")
            exc.status_code = status
            if isinstance(body, dict):
                exc.error_name = body.get("name")
                exc.error_message = body.get("message")
                exc.details = body.get("details")
            raise exc
        raise PayPalUncertainOutcomeError(
            f"PayPal returned HTTP {status}; outcome uncertain."
        )
    return _parse_payout_response(response.json())


def _is_definitive_rejection(exc) -> bool:
    """Whether a PayPalAPIError proves the payout was not executed.

    Only structured 4xx responses (other than 409/429) count as definitive
    validation rejections.  Transport, rate-limit, conflict, and unstructured
    responses remain uncertain.
    """
    status = getattr(exc, "status_code", None)
    if status is None:
        import re

        match = re.search(r"HTTP (\d+)", str(exc))
        if match:
            status = int(match.group(1))
    if status is None or status == 429 or status == 409:
        return False
    if not (400 <= status < 500):
        return False
    return bool(
        getattr(exc, "error_name", None)
        or getattr(exc, "error_message", None)
        or getattr(exc, "details", None)
    )


def _reconcile_with_paypal(
    reservation: PayoutReservation, django_settings, session=None
) -> tuple[str, str, str, str] | None:
    """Query PayPal batch/item status for a pending submission.

    Returns (batch_id, item_id, batch_status, item_transaction_status) or
    None if the batch is not found in PayPal.
    """
    if not reservation.paypal_payout_batch_id:
        return None
    client = PayPalClient.from_settings(django_settings, session=session)
    try:
        body = client.get(
            f"/v1/payments/payouts/{reservation.paypal_payout_batch_id}"
        ).json()
    except PayPalAPIError as exc:
        if isinstance(exc, PayPalConflictError):
            # 409 — duplicate batch id; treat as already submitted
            return (
                reservation.paypal_payout_batch_id,
                None,
                "SUBMITTED",
                None,
            )
        raise
    batch_header = body.get("batch_header", {}) or {}
    batch_id = batch_header.get("payout_batch_id") or reservation.paypal_payout_batch_id
    batch_status = batch_header.get("batch_status")
    item_id = reservation.paypal_payout_item_id
    item_transaction_status = None
    items = body.get("items", []) or []
    if items:
        item = items[0]
        if not item_id:
            item_id = item.get("payout_item_id")
        item_transaction_status = item.get("transaction_status")
    return batch_id, item_id, batch_status, item_transaction_status


@transaction.atomic
def submit_payout(
    reservation_id,
    django_settings,
    session=None,
):
    """Submit an existing PayoutReservation to PayPal Payouts v1 sandbox.

    Durable submission state (sender_batch_id, SUBMISSION_PENDING) is committed
    before any HTTP call.  Network calls happen outside the transaction.

    Returns a :class:`SubmissionResult`.

    Raises:
        PayoutFeatureDisabled: PayPal Payouts is not enabled or misconfigured.
        PayoutNotReserved: the reservation is not in a submittable state.
        PayoutAlreadySubmitted: the reservation has already been submitted.
    """
    _require_payouts_enabled(django_settings)

    # --- Phase 1: Lock, validate, transition to SUBMISSION_PENDING -------
    try:
        reservation = PayoutReservation.objects.select_for_update().get(
            pk=reservation_id
        )
    except PayoutReservation.DoesNotExist:
        raise PayoutNotReserved("Payout reservation not found.")

    now = timezone.now()

    if reservation.status == PayoutReservation.Status.SUBMITTED:
        return SubmissionResult(
            reservation,
            "already_submitted",
            paypal_batch_id=reservation.paypal_payout_batch_id,
            paypal_item_id=reservation.paypal_payout_item_id,
        )
    if reservation.status in (
        PayoutReservation.Status.COMPLETED,
        PayoutReservation.Status.FAILED,
    ):
        return SubmissionResult(
            reservation,
            "terminal",
            paypal_batch_id=reservation.paypal_payout_batch_id,
            paypal_item_id=reservation.paypal_payout_item_id,
            error=reservation.submission_error,
        )
    if reservation.status in (
        PayoutReservation.Status.SUBMISSION_PENDING,
        PayoutReservation.Status.UNCERTAIN,
    ):
        # A submission is already in flight or its outcome is uncertain.
        # Never re-POST; direct the caller to reconcile instead.
        return SubmissionResult(
            reservation,
            "pending",
            paypal_batch_id=reservation.paypal_payout_batch_id,
            paypal_item_id=reservation.paypal_payout_item_id,
        )

    if reservation.status == PayoutReservation.Status.RESERVED:
        # Re-validate eligibility before committing to submission.
        _validate_submission_eligibility(reservation, now)
        _transition_to_submission_pending(reservation)

    # --- Phase 2: Call PayPal (outside the transaction) ------------------
    try:
        batch_id, item_id, batch_status = _submit_to_paypal(
            reservation, django_settings, session=session
        )
    except PayPalUncertainOutcomeError:
        # Timeout, connection loss, or 5xx: we cannot prove whether PayPal
        # processed the request.  Transition to UNCERTAIN so the reservation
        # is recoverable via reconciliation or manual investigation.  Never
        # auto-retry POST.
        with transaction.atomic():
            reservation = PayoutReservation.objects.select_for_update().get(
                pk=reservation_id
            )
            _transition_to_uncertain(reservation)
            AuditEvent.record(
                AuditEvent.EventType.PAYMENT_FAILED,
                organization=reservation.organization,
                agent=reservation.spend_request.agent,
                spend_request=reservation.spend_request,
                actor_type=AuditEvent.ActorType.SYSTEM,
                actor_id="",
                amount=to_major(reservation.amount_minor, reservation.currency),
                currency=reservation.currency,
                merchant=reservation.spend_request.merchant_ref,
                payout_reservation_id=str(reservation.id),
                error="uncertain_outcome",
            )
        return SubmissionResult(
            reservation,
            "uncertain",
            paypal_batch_id=reservation.paypal_payout_batch_id,
            paypal_item_id=reservation.paypal_payout_item_id,
        )
    except PayPalAPIError as exc:
        # Rate limits, conflicts, transport-derived, and unstructured 4xx
        # responses are treated as uncertain.  Only definitive validation
        # rejections (structured 4xx) mark the reservation FAILED.
        uncertain = (
            isinstance(exc, PayPalRateLimitError)
            or getattr(exc, "status_code", None) == 429
            or not _is_definitive_rejection(exc)
        )
        with transaction.atomic():
            reservation = PayoutReservation.objects.select_for_update().get(
                pk=reservation_id
            )
            if uncertain:
                _transition_to_uncertain(reservation)
                AuditEvent.record(
                    AuditEvent.EventType.PAYMENT_FAILED,
                    organization=reservation.organization,
                    agent=reservation.spend_request.agent,
                    spend_request=reservation.spend_request,
                    actor_type=AuditEvent.ActorType.SYSTEM,
                    actor_id="",
                    amount=to_major(reservation.amount_minor, reservation.currency),
                    currency=reservation.currency,
                    merchant=reservation.spend_request.merchant_ref,
                    payout_reservation_id=str(reservation.id),
                    error="uncertain_outcome",
                )
                return SubmissionResult(
                    reservation,
                    "uncertain",
                    paypal_batch_id=reservation.paypal_payout_batch_id,
                    paypal_item_id=reservation.paypal_payout_item_id,
                )
            _transition_to_failed(reservation, str(exc))
            AuditEvent.record(
                AuditEvent.EventType.PAYMENT_FAILED,
                organization=reservation.organization,
                agent=reservation.spend_request.agent,
                spend_request=reservation.spend_request,
                actor_type=AuditEvent.ActorType.SYSTEM,
                amount=to_major(reservation.amount_minor, reservation.currency),
                currency=reservation.currency,
                merchant=reservation.spend_request.merchant_ref,
                payout_reservation_id=str(reservation.id),
                error=str(exc),
            )
        return SubmissionResult(
            reservation,
            "failed",
            error=str(exc),
        )

    # --- Phase 3: Batch accepted — store IDs, transition to SUBMITTED -----
    with transaction.atomic():
        reservation = PayoutReservation.objects.select_for_update().get(
            pk=reservation_id
        )
        _transition_to_submitted(reservation, batch_id, item_id)
        AuditEvent.record(
            AuditEvent.EventType.PAYMENT_EXECUTING,
            organization=reservation.organization,
            agent=reservation.spend_request.agent,
            spend_request=reservation.spend_request,
            actor_type=AuditEvent.ActorType.USER,
            actor_id="",
            amount=to_major(reservation.amount_minor, reservation.currency),
            currency=reservation.currency,
            merchant=reservation.spend_request.merchant_ref,
            destination_type=reservation.destination_type,
            destination_fingerprint=reservation.destination_fingerprint,
            payout_reservation_id=str(reservation.id),
            paypal_payout_batch_id=batch_id,
            paypal_payout_item_id=item_id,
            batch_status=batch_status,
        )

    return SubmissionResult(
        reservation,
        "submitted",
        paypal_batch_id=batch_id,
        paypal_item_id=item_id,
        batch_status=batch_status,
    )


@transaction.atomic
def reconcile_payout(
    reservation_id,
    django_settings,
    session=None,
):
    """Reconcile a pending/uncertain submission with PayPal.

    Queries PayPal batch/item status and advances the reservation to an
    authoritative state.  Unknown statuses keep the reservation recoverable.

    Returns a :class:`SubmissionResult`.
    """
    _require_payouts_enabled(django_settings)

    try:
        reservation = PayoutReservation.objects.select_for_update().get(
            pk=reservation_id
        )
    except PayoutReservation.DoesNotExist:
        raise PayoutNotReserved("Payout reservation not found.")

    if reservation.status in (
        PayoutReservation.Status.COMPLETED,
        PayoutReservation.Status.FAILED,
    ):
        return SubmissionResult(
            reservation,
            "reconciled",
            paypal_batch_id=reservation.paypal_payout_batch_id,
            paypal_item_id=reservation.paypal_payout_item_id,
            error=reservation.submission_error,
        )
    if reservation.status == PayoutReservation.Status.RESERVED:
        # Never submitted; nothing to reconcile.
        return SubmissionResult(reservation, "not_submitted")

    # SUBMISSION_PENDING or UNCERTAIN: query PayPal.
    try:
        result = _reconcile_with_paypal(reservation, django_settings, session=session)
    except PayPalClientError as exc:
        # Cannot reach PayPal (or PayPal rejected the lookup): keep current
        # state recoverable.  Never claim completion or failure.
        return SubmissionResult(
            reservation,
            "pending",
            paypal_batch_id=reservation.paypal_payout_batch_id,
            paypal_item_id=reservation.paypal_payout_item_id,
            error=str(exc),
        )

    if result is None:
        # Batch not found in PayPal: keep pending for retry.
        return SubmissionResult(
            reservation,
            "pending",
            paypal_batch_id=reservation.paypal_payout_batch_id,
            paypal_item_id=reservation.paypal_payout_item_id,
        )

    batch_id, item_id, batch_status, item_transaction_status = result
    status_upper = (batch_status or "").upper()
    item_status_upper = (item_transaction_status or "").upper()

    with transaction.atomic():
        reservation = PayoutReservation.objects.select_for_update().get(
            pk=reservation_id
        )
        reservation.paypal_payout_batch_id = (
            batch_id or reservation.paypal_payout_batch_id
        )
        if item_id:
            reservation.paypal_payout_item_id = item_id

        # --- Batch-level outcomes ---------------------------------------
        if status_upper in ("FAILED", "DENIED", "CANCELED", "REFUNDED"):
            # Batch was definitively rejected by PayPal.
            reservation.status = PayoutReservation.Status.FAILED
            reservation.submission_error = f"PayPal batch status: {batch_status}"
            outcome = "reconciled"
            AuditEvent.record(
                AuditEvent.EventType.PAYMENT_FAILED,
                organization=reservation.organization,
                agent=reservation.spend_request.agent,
                spend_request=reservation.spend_request,
                actor_type=AuditEvent.ActorType.PAYPAL,
                actor_id="",
                amount=to_major(reservation.amount_minor, reservation.currency),
                currency=reservation.currency,
                merchant=reservation.spend_request.merchant_ref,
                payout_reservation_id=str(reservation.id),
                paypal_payout_batch_id=batch_id,
                paypal_payout_item_id=item_id,
                batch_status=batch_status,
            )
        elif status_upper in ("SUCCESS", "COMPLETED"):
            # Batch accepted by PayPal — completion requires authoritative
            # item-level evidence.  Batch acceptance alone is NOT proof.
            if item_status_upper == "SUCCESS":
                # Authoritative item-level completion.
                reservation.status = PayoutReservation.Status.COMPLETED
                outcome = "reconciled"
                AuditEvent.record(
                    AuditEvent.EventType.PAYMENT_SUCCEEDED,
                    organization=reservation.organization,
                    agent=reservation.spend_request.agent,
                    spend_request=reservation.spend_request,
                    actor_type=AuditEvent.ActorType.PAYPAL,
                    actor_id="",
                    amount=to_major(reservation.amount_minor, reservation.currency),
                    currency=reservation.currency,
                    merchant=reservation.spend_request.merchant_ref,
                    payout_reservation_id=str(reservation.id),
                    paypal_payout_batch_id=batch_id,
                    paypal_payout_item_id=item_id,
                    batch_status=batch_status,
                )
            elif item_status_upper in (
                "FAILED",
                "DENIED",
                "CANCELED",
                "REFUNDED",
                "RETURNED",
                "REVERSED",
                "BLOCKED",
            ):
                # Batch processed but the individual item did not succeed.
                reservation.status = PayoutReservation.Status.FAILED
                reservation.submission_error = (
                    f"PayPal batch status: {batch_status}; "
                    f"item status: {item_transaction_status}"
                )
                outcome = "reconciled"
                AuditEvent.record(
                    AuditEvent.EventType.PAYMENT_FAILED,
                    organization=reservation.organization,
                    agent=reservation.spend_request.agent,
                    spend_request=reservation.spend_request,
                    actor_type=AuditEvent.ActorType.PAYPAL,
                    actor_id="",
                    amount=to_major(reservation.amount_minor, reservation.currency),
                    currency=reservation.currency,
                    merchant=reservation.spend_request.merchant_ref,
                    payout_reservation_id=str(reservation.id),
                    paypal_payout_batch_id=batch_id,
                    paypal_payout_item_id=item_id,
                    batch_status=batch_status,
                )
            else:
                # UNCLAIMED, CLAIMED, PENDING, ONHOLD, or unknown: keep
                # recoverable (nonterminal).
                reservation.status = PayoutReservation.Status.SUBMISSION_PENDING
                outcome = "pending"
        else:
            # PENDING, PROCESSING, or unknown batch status: keep recoverable.
            reservation.status = PayoutReservation.Status.SUBMISSION_PENDING
            outcome = "pending"

        reservation.reconciliation_metadata = {
            **(reservation.reconciliation_metadata or {}),
            "batch_status": batch_status,
            "item_transaction_status": item_transaction_status,
        }
        reservation.save()

    return SubmissionResult(
        reservation,
        outcome,
        paypal_batch_id=reservation.paypal_payout_batch_id,
        paypal_item_id=reservation.paypal_payout_item_id,
        batch_status=batch_status,
    )
