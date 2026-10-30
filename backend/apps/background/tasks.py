"""Smoke-test task for the Procrastinate foundation.

This task has no financial, approval, spend, or audit side effects. It exists
solely to verify that the worker can dequeue and execute a job end-to-end.
It is not registered as a periodic task and does not auto-schedule.
"""

from procrastinate.contrib.django import app


@app.task(queue="smoke")
def smoke_test(message: str = "ok") -> dict:
    """Return a fixed payload to confirm the worker executed the job.

    No database writes, no external calls. Safe to run anywhere.
    """
    return {"status": "ok", "echo": message}
