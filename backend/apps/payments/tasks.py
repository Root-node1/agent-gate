"""Background payment execution jobs."""

from procrastinate.contrib.django import app


@app.task(queue="payments", name="apps.payments.tasks.execute_payment")
def execute_payment(spend_request_id: str) -> str:
    """Run one approved spend request through the configured executor."""
    from .services import execute_spend_request

    return execute_spend_request(spend_request_id)
