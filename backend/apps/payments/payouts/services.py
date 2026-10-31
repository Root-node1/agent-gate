"""Payout reservation services (INT-13I).

Public API:
- :func:`reserve_payout` — atomically validates eligibility and creates a
  durable :class:`~apps.payments.payouts.models.PayoutReservation` for an
  approved SpendRequest.  Reservation does NOT transfer money and makes NO
  PayPal API call.

All financial and recipient values are immutable snapshots taken from the
SpendRequest at reservation time.
"""

from django.db import transaction
from django.utils import timezone

import engine
from apps.accounts.models import Organization
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.common.money import to_major
from apps.payees.models import DestinationType, Payee
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
        spend_request = SpendRequest.objects.select_for_update(of=("self",)).get(
            pk=spend_request_id, organization=organization
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
