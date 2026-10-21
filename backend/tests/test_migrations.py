from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.accounts.models import Organization
from apps.agents.models import Agent, ApiKey
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.policies.models import MerchantRule, Policy
from apps.spend.models import SpendRequest

AUDIT_TABLE = "audit_auditevent"
TRUNCATE_TRIGGER = "audit_auditevent_no_truncate"


class LegacyBackfillMigrationTests(TransactionTestCase):
    """Runs the legacy backfill against real legacy rows instead of trusting an empty table."""

    migrate_from = [("gate", "0001_initial")]
    migrate_to = [("gate", "0002_migrate_legacy_data")]

    def test_legacy_rows_are_backfilled(self):
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(self.migrate_from)
            legacy_apps = executor.loader.project_state(self.migrate_from).apps
            self.create_legacy_rows(legacy_apps)

            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_to)

            self.assert_backfilled()
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def create_legacy_rows(self, apps):
        LegacyAgent = apps.get_model("gate", "Agent")
        LegacyPolicy = apps.get_model("gate", "Policy")
        LegacyMerchantRule = apps.get_model("gate", "MerchantRule")
        LegacySpendRequest = apps.get_model("gate", "SpendRequest")
        LegacyApproval = apps.get_model("gate", "Approval")
        LegacyAuditEvent = apps.get_model("gate", "AuditEvent")

        agent = LegacyAgent.objects.create(
            name="legacy-agent",
            api_key_prefix="legacy01",
            api_key_hash="a" * 64,
            status="active",
        )
        policy = LegacyPolicy.objects.create(
            agent=agent,
            currency="JPY",
            per_transaction_cap=Decimal("500.00"),
            approval_threshold=Decimal("500.00"),
            daily_budget=Decimal("1000.00"),
            monthly_budget=Decimal("5000.00"),
        )
        LegacyMerchantRule.objects.create(
            policy=policy, merchant="shop.example", action="allow", note="known merchant"
        )
        spend = LegacySpendRequest.objects.create(
            agent=agent,
            amount=Decimal("500.00"),
            currency="JPY",
            merchant="shop.example",
            purpose="pencils",
            source="untrusted",
            risk_score=42,
            decision="allow",
            reasons=["under cap"],
            matched_rules=["R01"],
            paypal_reference="REF-1",
        )
        LegacyApproval.objects.create(spend_request=spend, outcome="approved", note="ok")
        LegacyAuditEvent.objects.create(
            event_type="request.received",
            payload={"request": str(spend.pk)},
            agent=agent,
            spend_request=spend,
        )

    def assert_backfilled(self):
        organization = Organization.objects.get(name="Legacy")
        agent = Agent.objects.get(name="legacy-agent")
        self.assertEqual(agent.organization_id, organization.id)

        key = ApiKey.objects.get(agent=agent)
        self.assertIsNotNone(key.revoked_at)

        policy = Policy.objects.get(agent=agent)
        self.assertEqual(policy.currency, "JPY")
        self.assertEqual(policy.per_transaction_cap_minor, 500)
        self.assertEqual(policy.daily_budget_minor, 1000)
        self.assertEqual(policy.monthly_budget_minor, 5000)

        rule = MerchantRule.objects.get(policy=policy)
        self.assertEqual(rule.merchant_ref, "shop.example")
        self.assertEqual(rule.kind, "allow")

        spend = SpendRequest.objects.get(merchant_ref="shop.example")
        self.assertEqual(spend.amount_minor, 500)
        self.assertEqual(spend.decision, "allow")
        self.assertEqual(spend.status, "approved")
        self.assertEqual(spend.source_type, "web_page")
        self.assertEqual(spend.risk_score, 42)
        self.assertEqual(spend.paypal_reference, "REF-1")

        approval = Approval.objects.get(spend_request=spend)
        self.assertEqual(approval.outcome, "approved")
        self.assertEqual(approval.organization_id, organization.id)

        event = AuditEvent.objects.get(event_type="request.received")
        self.assertEqual(event.organization_id, organization.id)
        self.assertEqual(event.agent_id, agent.id)

    def _audit_trigger_exists(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_trigger WHERE tgname = %s AND tgrelid = to_regclass(%s)",
                [TRUNCATE_TRIGGER, AUDIT_TABLE],
            )
            return cursor.fetchone() is not None

    def _fixture_teardown(self):
        disabled = connection.vendor == "postgresql" and self._audit_trigger_exists()
        if disabled:
            with connection.cursor() as cursor:
                cursor.execute(f"ALTER TABLE {AUDIT_TABLE} DISABLE TRIGGER {TRUNCATE_TRIGGER}")
        try:
            super()._fixture_teardown()
        finally:
            if disabled and self._audit_trigger_exists():
                with connection.cursor() as cursor:
                    cursor.execute(f"ALTER TABLE {AUDIT_TABLE} ENABLE TRIGGER {TRUNCATE_TRIGGER}")
