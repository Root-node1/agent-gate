"""Smoke tests for the Procrastinate background-job foundation.

These tests verify real enqueue/consume behavior against a PostgreSQL test
database. They use PostgresTransactionTestCase (not TestCase) because
Procrastinate uses SELECT FOR UPDATE internally, which Django's TestCase
serializes away, and because the append-only audit table requires special
flush handling.
"""

import asyncio
import contextlib
from io import StringIO
from unittest import skipUnless

from asgiref.sync import sync_to_async
from django.db import connection, connections
from procrastinate.contrib.django import app
from procrastinate.contrib.django.models import ProcrastinateJob

from apps.background.tasks import smoke_test
from tests.base import PostgresTransactionTestCase

PG_REQUIRED = "Procrastinate requires a PostgreSQL backend (LISTEN/NOTIFY)."


@app.task(queue="smoke", name="smoke_fail_test_only")
def _smoke_fail(message: str = "fail"):
    """TEST-ONLY task that always raises. Not registered as periodic."""
    raise ValueError(f"smoke-test intentional failure: {message}")


@skipUnless(connection.vendor == "postgresql", PG_REQUIRED)
class ProcrastinateSchemaTests(PostgresTransactionTestCase):
    """Verify Procrastinate's PostgreSQL schema was created by migrations."""

    def tearDown(self):
        super().tearDown()
        app.close()
        connections.close_all()

    def test_pg_class_has_procrastinate_tables(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE tablename LIKE 'procrastinate_%'"
            )
            tables = {row[0] for row in cursor.fetchall()}
        self.assertIn("procrastinate_jobs", tables)
        self.assertIn("procrastinate_events", tables)
        self.assertIn("procrastinate_periodic_defers", tables)
        self.assertIn("procrastinate_workers", tables)

    def test_healthchecks_pass(self):
        """Verify Procrastinate health checks against the PostgreSQL database.

        We invoke the health-check logic directly rather than via
        ``call_command("procrastinate", "healthchecks")``.  The management
        command internally creates a ``PsycopgConnector``, opens its async pool,
        and runs the health-check function through ``sync_to_async`` in a worker
        thread.  Inside that thread, ``check_connection()`` (sync) routes
        through ``async_to_sync`` on a *nested* event loop.  A psycopg
        connection acquired on that nested loop is not returned to the pool
        before the pool is closed, leaking a PostgreSQL session that blocks
        test-database teardown.

        By managing the connector lifecycle in a single ``asyncio.run`` and
        calling ``check_connection_async()`` (which runs on the same event loop
        as the pool), we avoid the cross-loop leak entirely.
        """

        def _db_checks():
            from django.db.migrations import executor as executor_module
            from procrastinate import exceptions as pr_exc

            conn = connections["default"]
            conn.ensure_connection()
            print("Database connection: OK")
            try:
                executor = executor_module.MigrationExecutor(conn)
                plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
                missing = "procrastinate" in {
                    mig.app_label for mig, _ in plan
                }
                if missing:
                    raise pr_exc.ConnectorException(
                        "Missing procrastinate migrations."
                    )
                print("Migrations: OK")
            finally:
                # ``_db_checks`` runs in a sync_to_async worker thread. The
                # Django connection it opens is thread-local, so the main
                # thread's ``connections.close_all()`` in tearDown cannot see
                # it. Close it here, on the thread that opened it, otherwise
                # the session blocks test-database teardown.
                connections.close_all()

        worker_connector = app.connector.get_worker_connector()
        out = StringIO()
        with contextlib.redirect_stdout(out):
            with app.replace_connector(worker_connector):

                async def _run_healthchecks():
                    async with app.open_async():
                        await sync_to_async(_db_checks)()

                        await app.check_connection_async()
                        print("Default Django Procrastinate App: OK")

                        await app.check_connection_async()
                        print("Worker App: OK")

                asyncio.run(_run_healthchecks())
        output = out.getvalue()
        self.assertIn("Database connection: OK", output)
        self.assertIn("Migrations: OK", output)
        self.assertIn("Worker App: OK", output)


@skipUnless(connection.vendor == "postgresql", PG_REQUIRED)
class SmokeTaskExecutionTests(PostgresTransactionTestCase):
    """Verify the worker can enqueue, execute, and observe job lifecycle."""

    def setUp(self):
        super().setUp()
        with connection.cursor() as cursor:
            cursor.execute(
                "TRUNCATE procrastinate_jobs, procrastinate_events, "
                "procrastinate_periodic_defers, procrastinate_workers "
                "RESTART IDENTITY CASCADE"
            )

    def tearDown(self):
        super().tearDown()
        app.close()
        connections.close_all()

    def _run_worker(self):
        with app.replace_connector(app.connector.get_worker_connector()):
            app.run_worker(
                queues=["smoke"],
                wait=False,
                install_signal_handlers=False,
                listen_notify=False,
            )
        app.close()
        connections.close_all()

    def test_job_reaches_succeeded_state(self):
        smoke_test.defer(message="hello")
        self._run_worker()

        job = ProcrastinateJob.objects.get(
            task_name="apps.background.tasks.smoke_test"
        )
        self.assertEqual(job.status, "succeeded")

    def test_failed_job_is_observable(self):
        _smoke_fail.defer(message="boom")
        self._run_worker()

        job = ProcrastinateJob.objects.get(task_name="smoke_fail_test_only")
        self.assertEqual(job.status, "failed")

    def test_duplicate_defers_do_not_collide(self):
        """Deferring the same task twice creates two independent, successful jobs."""
        smoke_test.defer(message="first")
        smoke_test.defer(message="second")
        self._run_worker()

        jobs = ProcrastinateJob.objects.filter(
            task_name="apps.background.tasks.smoke_test"
        )
        self.assertEqual(jobs.count(), 2)
        for job in jobs:
            self.assertEqual(job.status, "succeeded")

    def test_re_run_worker_finds_no_leftover_todo_jobs(self):
        """A second worker pass should find nothing to do (no duplicate execution)."""
        smoke_test.defer(message="once")
        self._run_worker()

        todo_count = ProcrastinateJob.objects.filter(
            status="todo", queue_name="smoke"
        ).count()
        self.assertEqual(todo_count, 0)

        self._run_worker()
        self.assertEqual(
            ProcrastinateJob.objects.filter(status="succeeded").count(), 1
        )
