from django.apps import apps
from django.db import connection
from django.test import TestCase

LEGACY_TABLES = (
    "gate_agent",
    "gate_policy",
    "gate_merchantrule",
    "gate_spendrequest",
    "gate_approval",
    "gate_auditevent",
)


class LegacyGateRetirementTests(TestCase):
    def test_gate_app_is_not_installed(self):
        self.assertFalse(apps.is_installed("gate"))
        self.assertNotIn("gate", {config.label for config in apps.get_app_configs()})

    def test_a_fresh_database_has_no_legacy_tables(self):
        tables = set(connection.introspection.table_names())
        self.assertEqual(tables.intersection(LEGACY_TABLES), set())
