"""Procrastinate background tasks for AgentGate.

Two tasks live here, both discovered by the Procrastinate Django integration
(via the ``tasks`` autodiscover hook):

- ``smoke_test``: enqueue/consume smoke test (see ``tests/test_procrastinate_smoke.py``).
- ``expire_approvals_periodic``: a *periodic* task that expires overdue pending
  approvals every ~60 seconds. It delegates to the existing idempotent
  ``apps.approvals.services.expire_due`` service; see the docstring below and
  ``OPERATIONS.md`` (scheduling & cron-coexistence plan).
"""

import logging

from procrastinate import RetryStrategy
from procrastinate.contrib.django import app

logger = logging.getLogger(__name__)


@app.task(queue="smoke")
def smoke_test(message: str = "ok") -> dict:
    """Return a fixed payload to confirm the worker executed the job.

    No database writes, no external calls. Safe to run anywhere.
    """
    return {"status": "ok", "echo": message}


# ---------------------------------------------------------------------------
# Periodic approval-expiration task (INT-12D.1)
# ---------------------------------------------------------------------------
# Schedule: every minute (Procrastinate cron supports an optional 6th seconds
# column; a 5-column "*/1 * * * *" yields a 60-second interval, matching the
# cadence documented for the legacy ``expire_approvals`` management command).
APPROVAL_EXPIRY_CRON = "*/1 * * * *"
APPROVAL_EXPIRY_PERIODIC_ID = "approval_expiry"
APPROVAL_EXPIRY_QUEUE = "approvals"
# Transient DB errors (e.g. SELECT FOR UPDATE deadlocks under load) warrant a
# bounded retry. expire_due is idempotent, so retries cannot double-expire a
# given approval or emit duplicate APPROVAL_EXPIRED audit events.
APPROVAL_EXPIRY_MAX_ATTEMPTS = 3
APPROVAL_EXPIRY_QUEUEING_LOCK = "approval_expiry"


@app.periodic(
    cron=APPROVAL_EXPIRY_CRON,
    periodic_id=APPROVAL_EXPIRY_PERIODIC_ID,
)
@app.task(
    queue=APPROVAL_EXPIRY_QUEUE,
    name="apps.background.tasks.expire_approvals_periodic",
    retry=RetryStrategy(max_attempts=APPROVAL_EXPIRY_MAX_ATTEMPTS, wait=1),
    queueing_lock=APPROVAL_EXPIRY_QUEUEING_LOCK,
)
def expire_approvals_periodic(timestamp: int) -> int:
    """Periodically expire overdue pending approvals (~every 60 seconds).

    Delegates to ``apps.approvals.services.expire_due``, preserving its default
    ``limit=1000`` and its row-level (``SELECT FOR UPDATE``) locking behavior.
    ``expire_due`` is idempotent: it selects only ``PENDING`` approvals whose
    deadline has passed and re-checks state inside a per-approval transaction
    before transitioning, so repeated execution (including retries up to
    ``APPROVAL_EXPIRY_MAX_ATTEMPTS``) produces exactly one ``APPROVAL_EXPIRED``
    audit event per approval. No payment or webhook side effects.

    Procrastinate guarantees each scheduled occurrence is deferred at most once
    (the periodic deferrer dedups on ``(periodic_id, defer_timestamp)`` via
    ``defer_periodic_job``), and the ``queueing_lock`` prevents expiry jobs from
    accumulating in the queue if a run is still pending.
    """
    from apps.approvals.services import expire_due

    return expire_due()
