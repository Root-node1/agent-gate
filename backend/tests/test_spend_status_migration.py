from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from tests.base import PostgresTransactionTestCase

MIGRATION_FROM = ("spend", "0003_source_untrusted")
MIGRATION_TO = ("spend", "0004_spendrequest_blocked_status")


class SpendStatusMigrationTests(PostgresTransactionTestCase):
    migrate_from = MIGRATION_FROM
    migrate_to = MIGRATION_TO

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.latest_targets = self.executor.loader.graph.leaf_nodes()
        self.old_targets = [
            self.migrate_from if app_label == self.migrate_to[0] else (app_label, name)
            for app_label, name in self.latest_targets
        ]
        self.executor.migrate(self.old_targets)
        self.old_apps = self.executor.loader.project_state(self.old_targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.latest_targets)
        super().tearDown()

    def create_spend_request(self, *, status):
        Organization = self.old_apps.get_model("accounts", "Organization")
        Agent = self.old_apps.get_model("agents", "Agent")
        Policy = self.old_apps.get_model("policies", "Policy")
        SpendRequest = self.old_apps.get_model("spend", "SpendRequest")

        organization = Organization.objects.create(name="migration-test")
        agent = Agent.objects.create(name="migration-agent", organization_id=organization.pk)
        policy = Policy.objects.create(
            organization_id=organization.pk,
            agent_id=agent.pk,
        )
        return SpendRequest.objects.create(
            organization_id=organization.pk,
            agent_id=agent.pk,
            policy_id=policy.pk,
            policy_version=policy.version,
            amount_minor=100,
            merchant_ref="example.test",
            decision="allow",
            status=status,
        )

    def test_forward_converts_legacy_blocked_rows(self):
        spend_request = self.create_spend_request(status="blocked")
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.latest_targets)

        SpendRequest = self.executor.loader.project_state(self.latest_targets).apps.get_model(
            "spend", "SpendRequest"
        )
        self.assertEqual(
            SpendRequest.objects.get(pk=spend_request.pk).status,
            "execution_blocked",
        )

    def test_reverse_converts_execution_blocked_rows(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.latest_targets)
        new_apps = self.executor.loader.project_state(self.latest_targets).apps
        Organization = new_apps.get_model("accounts", "Organization")
        Agent = new_apps.get_model("agents", "Agent")
        Policy = new_apps.get_model("policies", "Policy")
        SpendRequest = new_apps.get_model("spend", "SpendRequest")

        organization = Organization.objects.create(name="reverse-migration-test")
        agent = Agent.objects.create(name="reverse-agent", organization_id=organization.pk)
        policy = Policy.objects.create(
            organization_id=organization.pk,
            agent_id=agent.pk,
        )
        spend_request = SpendRequest.objects.create(
            organization_id=organization.pk,
            agent_id=agent.pk,
            policy_id=policy.pk,
            policy_version=policy.version,
            amount_minor=100,
            merchant_ref="example.test",
            decision="allow",
            status="execution_blocked",
        )

        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.old_targets)
        old_spend_request = self.executor.loader.project_state(self.old_targets).apps.get_model(
            "spend", "SpendRequest"
        )
        self.assertEqual(
            old_spend_request.objects.get(pk=spend_request.pk).status,
            "blocked",
        )
