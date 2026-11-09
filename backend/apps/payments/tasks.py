"""Background payment execution and reconciliation jobs."""

from dataclasses import asdict

from procrastinate import RetryStrategy
from procrastinate.contrib.django import app


@app.task(queue="payments", name="apps.payments.tasks.execute_payment")
def execute_payment(spend_request_id: str) -> str:
    """Run one approved spend request through the configured executor."""
    from .services import execute_spend_request

    return execute_spend_request(spend_request_id)


@app.task(queue="payments", name="apps.payments.tasks.process_webhook_event")
def process_webhook_event(webhook_event_id: str) -> str:
    """Apply one stored PayPal webhook event."""
    from .webhook_service import apply_webhook_event

    return apply_webhook_event(webhook_event_id)


PAYMENT_RECONCILIATION_CRON = "*/5 * * * *"
PAYMENT_RECONCILIATION_PERIODIC_ID = "payment_reconciliation"
PAYMENT_RECONCILIATION_QUEUEING_LOCK = "payment_reconciliation"


@app.periodic(
    cron=PAYMENT_RECONCILIATION_CRON,
    periodic_id=PAYMENT_RECONCILIATION_PERIODIC_ID,
)
@app.task(
    queue="payments",
    name="apps.payments.tasks.reconcile_payments_periodic",
    retry=RetryStrategy(max_attempts=3, wait=2),
    queueing_lock=PAYMENT_RECONCILIATION_QUEUEING_LOCK,
)
def reconcile_payments_periodic(timestamp: int) -> dict:
    """Query PayPal for stale executing payments and apply terminal results."""
    from .reconciliation import reconcile_payments

    return asdict(reconcile_payments())


WEBHOOK_RETENTION_CRON = "30 3 * * *"
WEBHOOK_RETENTION_PERIODIC_ID = "webhook_retention"
WEBHOOK_RETENTION_QUEUEING_LOCK = "webhook_retention"


@app.periodic(
    cron=WEBHOOK_RETENTION_CRON,
    periodic_id=WEBHOOK_RETENTION_PERIODIC_ID,
)
@app.task(
    queue="payments",
    name="apps.payments.tasks.purge_webhook_payloads_periodic",
    retry=RetryStrategy(max_attempts=3, wait=2),
    queueing_lock=WEBHOOK_RETENTION_QUEUEING_LOCK,
)
def purge_webhook_payloads_periodic(timestamp: int) -> int:
    """Clear payloads for processed webhook events past the retention window."""
    from .retention import purge_processed_webhook_payloads

    return purge_processed_webhook_payloads()
