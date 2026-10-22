"""Approve, deny, and expire requests with a fresh policy and budget check."""

from django.db import transaction
from django.utils import timezone

import engine
from apps.accounts.models import OrgMembership
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.common.money import to_major
from apps.payees.models import Payee
from apps.spend import services as spend_services
from apps.spend.models import SpendRequest

from .models import Approval

APPROVER_ROLES = (OrgMembership.Role.ADMIN, OrgMembership.Role.APPROVER)


class ApprovalError(Exception):
    """Base class for approval workflow failures."""


class ApprovalNotFound(ApprovalError):
    """The approval is missing or the user cannot see it."""


class ApprovalConflict(ApprovalError):
    """The approval is no longer pending, or the action conflicts with its outcome."""


class ApprovalExpired(ApprovalError):
    """The approval deadline has passed."""


class ApprovalRecheckFailed(ApprovalError):
    """Current state no longer permits execution."""

    def __init__(self, message: str, rules: list[str] | None = None):
        super().__init__(message)
        self.rules = rules or []


def _requester_may_decide(user, organization_id) -> bool:
    return user.memberships.filter(
        organization_id=organization_id, role__in=APPROVER_ROLES
    ).exists()


def _locked_records(approval_id, user):
    """Load the approval under the documented agent -> policy -> spend -> approval order."""
    try:
        stub = Approval.objects.values("spend_request_id", "organization_id").get(pk=approval_id)
    except Approval.DoesNotExist:
        raise ApprovalNotFound("Approval not found.") from None
    if not _requester_may_decide(user, stub["organization_id"]):
        raise ApprovalNotFound("Approval not found.")
    try:
        agent_id = (
            SpendRequest.objects.only("agent_id").get(pk=stub["spend_request_id"]).agent_id
        )
    except SpendRequest.DoesNotExist:
        raise ApprovalNotFound("Approval not found.") from None
    agent = Agent.objects.select_for_update().get(pk=agent_id)
    policy = spend_services.current_policy(agent, for_update=True)
    try:
        spend_request = SpendRequest.objects.select_for_update().get(
            pk=stub["spend_request_id"]
        )
        approval = Approval.objects.select_for_update().get(pk=approval_id)
    except (SpendRequest.DoesNotExist, Approval.DoesNotExist):
        raise ApprovalNotFound("Approval not found.") from None
    return approval, spend_request, agent, policy


def _expire_locked(approval: Approval, spend_request: SpendRequest, now) -> None:
    approval.outcome = Approval.Outcome.EXPIRED
    approval.decided_at = now
    approval.save(update_fields=["outcome", "decided_at", "updated_at"])
    spend_request.status = SpendRequest.Status.EXPIRED
    spend_request.save(update_fields=["status", "updated_at"])
    AuditEvent.record(
        AuditEvent.EventType.APPROVAL_EXPIRED,
        organization=approval.organization,
        agent=spend_request.agent,
        spend_request=spend_request,
        actor_type=AuditEvent.ActorType.SYSTEM,
    )


def _recheck_failure(spend_request: SpendRequest, agent, policy, now) -> list[str] | None:
    """Return rule ids that now deny, or a destination-change marker."""
    if spend_request.destination_fingerprint:
        payee = Payee.objects.filter(
            organization_id=spend_request.organization_id,
            merchant_ref=spend_request.merchant_ref,
        ).only("destination_fingerprint").first()
        if payee and payee.destination_fingerprint != spend_request.destination_fingerprint:
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


def decide(approval_id, *, user, approve: bool, note: str = "") -> tuple[Approval, bool]:
    """Approve or deny once. Returns (approval, changed); same-outcome retries are no-ops."""
    outcome = Approval.Outcome.APPROVED if approve else Approval.Outcome.DENIED
    expired = False
    with transaction.atomic():
        approval, spend_request, agent, policy = _locked_records(approval_id, user)
        if approval.outcome == outcome:
            return approval, False
        if approval.outcome != Approval.Outcome.PENDING:
            raise ApprovalConflict(f"This approval is already {approval.outcome}.")
        if spend_request.status != SpendRequest.Status.PENDING_APPROVAL:
            raise ApprovalConflict("The spend request is no longer pending approval.")

        now = timezone.now()
        if approval.expires_at <= now:
            _expire_locked(approval, spend_request, now)
            expired = True
        else:
            if approve:
                if policy is None:
                    raise ApprovalRecheckFailed("This agent has no current policy.")
                try:
                    failed_rules = _recheck_failure(spend_request, agent, policy, now)
                except Exception:
                    raise ApprovalRecheckFailed(
                        "The current policy could not be evaluated."
                    ) from None
                if failed_rules:
                    raise ApprovalRecheckFailed(
                        "Current policy or destination state no longer permits approval.",
                        failed_rules,
                    )
                spend_request.status = SpendRequest.Status.APPROVED
            else:
                spend_request.status = SpendRequest.Status.REJECTED

            approval.outcome = outcome
            approval.approver = user
            approval.note = note
            approval.decided_at = now
            approval.save(
                update_fields=["outcome", "approver", "note", "decided_at", "updated_at"]
            )
            spend_request.save(update_fields=["status", "updated_at"])
            AuditEvent.record(
                AuditEvent.EventType.APPROVAL_APPROVED
                if approve
                else AuditEvent.EventType.APPROVAL_DENIED,
                organization=approval.organization,
                agent=spend_request.agent,
                spend_request=spend_request,
                actor_type=AuditEvent.ActorType.USER,
                actor_id=str(user.pk),
                note=note,
            )
    if expired:
        raise ApprovalExpired("This approval has expired.")
    return approval, True


def expire_due(*, now=None, limit: int = 1_000) -> int:
    """Expire pending approvals whose deadline has passed. Safe to run repeatedly."""
    now = now or timezone.now()
    approval_ids = list(
        Approval.objects.filter(
            outcome=Approval.Outcome.PENDING, expires_at__lte=now
        )
        .order_by("expires_at")
        .values_list("pk", flat=True)[:limit]
    )
    expired = 0
    for approval_id in approval_ids:
        with transaction.atomic():
            try:
                stub = Approval.objects.values("spend_request_id").get(pk=approval_id)
                agent_id = (
                    SpendRequest.objects.only("agent_id")
                    .get(pk=stub["spend_request_id"])
                    .agent_id
                )
                Agent.objects.select_for_update().get(pk=agent_id)
                spend_request = SpendRequest.objects.select_for_update().get(
                    pk=stub["spend_request_id"]
                )
                approval = Approval.objects.select_for_update().get(pk=approval_id)
            except (Approval.DoesNotExist, SpendRequest.DoesNotExist, Agent.DoesNotExist):
                continue
            if approval.outcome != Approval.Outcome.PENDING or approval.expires_at > now:
                continue
            _expire_locked(approval, spend_request, now)
            expired += 1
    return expired
