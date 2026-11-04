"""Background payment execution jobs."""

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
