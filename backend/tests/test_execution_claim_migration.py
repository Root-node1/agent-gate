from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from tests.base import PostgresTransactionTestCase

MIGRATION_FROM = ("payments", "0006_merge_20261109_1903")
MIGRATION_TO = ("payments", "0007_shared_spend_execution_claim")


class SpendExecutionClaimMigrationTests(PostgresTransactionTestCase):
    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.latest_targets = self.executor.loader.graph.leaf_nodes()
        self.old_targets = [
            MIGRATION_FROM
            if app_label == MIGRATION_TO[0]
            else (app_label, name)
            for app_label, name in self.latest_targets
        ]
        self.executor.migrate(self.old_targets)
        self.old_apps = self.executor.loader.project_state(self.old_targets).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(self.latest_targets)
        super().tearDown()

    def test_forward_backfills_manual_and_automatic_claims(self):
        Organization = self.old_apps.get_model("accounts", "Organization")
        Agent = self.old_apps.get_model("agents", "Agent")
        Policy = self.old_apps.get_model("policies", "Policy")
        Payee = self.old_apps.get_model("payees", "Payee")
        SpendRequest = self.old_apps.get_model("spend", "SpendRequest")
        PayoutReservation = self.old_apps.get_model(
            "payments", "PayoutReservation"
        )

        organization = Organization.objects.create(name="claim-migration")
        agent = Agent.objects.create(
            name="claim-agent", organization_id=organization.pk
        )
        policy = Policy.objects.create(
            organization_id=organization.pk,
            agent_id=agent.pk,
        )

        def create_spend(status, merchant_ref):
            return SpendRequest.objects.create(
                organization_id=organization.pk,
                agent_id=agent.pk,
                policy_id=policy.pk,
                policy_version=policy.version,
                amount_minor=100,
                merchant_ref=merchant_ref,
                decision="allow",
                status=status,
            )

        executing = create_spend("executing", "executing.test")
        succeeded = create_spend("succeeded", "succeeded.test")
        manual = create_spend("approved", "manual.test")
        approved_without_claim = create_spend("approved", "unclaimed.test")
        payee = Payee.objects.create(
            organization_id=organization.pk,
            merchant_ref="manual.test",
            destination_type="paypal_email",
            destination_value="payee@example.test",
            destination_fingerprint="fingerprint",
        )
        reservation = PayoutReservation.objects.create(
            organization_id=organization.pk,
            spend_request_id=manual.pk,
            payee_id=payee.pk,
            amount_minor=100,
            currency="USD",
            destination_type="paypal_email",
            destination_value="payee@example.test",
            destination_fingerprint="fingerprint",
            status="reserved",
        )

        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.latest_targets)
        new_apps = self.executor.loader.project_state(self.latest_targets).apps
        Claim = new_apps.get_model("payments", "SpendExecutionClaim")

        self.assertEqual(
            Claim.objects.get(spend_request_id=executing.pk).status,
            "claimed",
        )
        self.assertEqual(
            Claim.objects.get(spend_request_id=succeeded.pk).status,
            "succeeded",
        )
        manual_claim = Claim.objects.get(spend_request_id=manual.pk)
        self.assertEqual(manual_claim.path, "manual")
        self.assertEqual(manual_claim.status, "claimed")
        self.assertEqual(manual_claim.payout_reservation_id, reservation.pk)
        self.assertFalse(Claim.objects.filter(
            spend_request_id=approved_without_claim.pk
        ).exists())
