"""Reconcile executing payments by querying the provider, never by retrying them."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.spend.models import SpendRequest

from .executors import build_paypal_client
from .paypal import PayPalError, get_payout_batch
from .services import ExecutionOutcome, reconcile_spend_request

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 100
DEFAULT_OLDER_THAN_MINUTES = 5


@dataclass
class ReconciliationSummary:
    """Counts from one reconciliation pass."""

    candidates: int = 0
    checked: int = 0
    succeeded: int = 0
    failed: int = 0
    still_executing: int = 0
    skipped: int = 0
    errors: int = 0
    unreferenced: int = 0
    dry_run: bool = False
    skipped_reason: str = ""


def find_candidates(*, limit: int, older_than_minutes: int):
    """Return executing rows old enough to check and the count without a reference."""
    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    stale = SpendRequest.objects.filter(
        status=SpendRequest.Status.EXECUTING,
        updated_at__lte=cutoff,
    )
    unreferenced = stale.filter(
        Q(paypal_reference__isnull=True) | Q(paypal_reference="")
    ).count()
    candidates = list(
        stale.exclude(Q(paypal_reference__isnull=True) | Q(paypal_reference=""))
        .order_by("updated_at")
        .values_list("pk", "paypal_reference")[:limit]
    )
    return unreferenced, candidates


def reconcile_payments(
    *,
    limit: int = DEFAULT_LIMIT,
    older_than_minutes: int = DEFAULT_OLDER_THAN_MINUTES,
    dry_run: bool = False,
) -> ReconciliationSummary:
    """Query PayPal for stale executing payments and apply forward-only results.

    A payment without a provider reference cannot be looked up; it stays
    executing and is reported for operator follow-up because a webhook is the
    only safe way to resolve it.
    """
    if getattr(settings, "PAYMENT_EXECUTOR", "fake") != "paypal":
        return ReconciliationSummary(skipped_reason="executor_not_paypal")

    unreferenced, candidates = find_candidates(
        limit=limit,
        older_than_minutes=older_than_minutes,
    )
    summary = ReconciliationSummary(
        candidates=len(candidates),
        unreferenced=unreferenced,
        dry_run=dry_run,
    )
    if dry_run or not candidates:
        return summary

    client = build_paypal_client()
    try:
        for spend_request_id, reference in candidates:
            summary.checked += 1
            try:
                result = get_payout_batch(client, reference)
            except PayPalError as exc:
                summary.errors += 1
                logger.warning(
                    "Could not reconcile payment %s: %s", spend_request_id, exc
                )
                continue
            if result.reference != reference:
                summary.errors += 1
                logger.warning(
                    "Payment %s received a different provider reference.",
                    spend_request_id,
                )
                continue
            try:
                outcome = reconcile_spend_request(
                    spend_request_id,
                    reference=result.reference,
                    provider_status=result.status,
                )
            except Exception:
                summary.errors += 1
                logger.exception(
                    "Could not apply reconciled state for payment %s.",
                    spend_request_id,
                )
                continue
            if outcome == ExecutionOutcome.SUCCEEDED:
                summary.succeeded += 1
            elif outcome == ExecutionOutcome.FAILED:
                summary.failed += 1
            elif outcome == ExecutionOutcome.EXECUTING:
                summary.still_executing += 1
            else:
                summary.skipped += 1
    finally:
        client.close()
    return summary
