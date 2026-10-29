from concurrent.futures import ThreadPoolExecutor
from unittest import mock, skipUnless

from django.db import close_old_connections, connection
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.policies.models import MerchantRule, Policy
from apps.policies.serializers import PolicyCreateSerializer
from apps.policies.services import PolicyConflictError, create_policy_version
from tests.base import PostgresTransactionTestCase, force_mfa


def _valid_payload(agent_id, **overrides):
    payload = {
        "agent": str(agent_id),
        "name": "Restrictive policy",
        "currency": "USD",
        "per_transaction_cap": "100.00",
        "approval_threshold": "50.00",
        "daily_budget": "500.00",
        "weekly_budget": "2000.00",
        "monthly_budget": "5000.00",
        "merchant_window_cap": "100.00",
        "merchant_mode": "blocklist",
        "velocity_max_count": 0,
        "velocity_window_seconds": 3600,
        "new_payee_cooldown_hours": 0,
        "untrusted_source_action": "needs_approval",
        "injection_escalate_threshold": 60,
        "classifier_required": False,
        "approval_ttl_minutes": 60,
        "timezone": "Africa/Nairobi",
        "merchant_rules": [
            {"merchant_ref": "https://www.acme.com/checkout", "kind": "allow", "note": "vendor"},
            {"merchant_ref": "evil.com", "kind": "block"},
        ],
    }
    payload.update(overrides)
    return payload


class PolicyCreateTestBase(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, self.raw_key = Agent.create_with_key("shopper", self.organization)
        self.existing_policy = Policy.objects.create(
            agent=self.agent, weekly_budget_minor=123_400
        )
        MerchantRule.objects.create(
            policy=self.existing_policy, merchant_ref="acme.com", kind=MerchantRule.Kind.ALLOW
        )

        self.admin = User.objects.create_user("admin")
        OrgMembership.objects.create(
            user=self.admin, organization=self.organization, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.admin)

        self.viewer = User.objects.create_user("viewer")
        OrgMembership.objects.create(
            user=self.viewer, organization=self.organization, role=OrgMembership.Role.VIEWER
        )

        self.other_org = Organization.objects.create(name="other-org")
        self.other_admin = User.objects.create_user("other-admin")
        OrgMembership.objects.create(
            user=self.other_admin, organization=self.other_org, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.other_admin)
        self.other_agent, _ = Agent.create_with_key("foreign-agent", self.other_org)

        self.client.force_authenticate(user=self.admin)
        self.valid = _valid_payload(self.agent.id)


class PolicyCreateSuccessTests(PolicyCreateTestBase):
    def test_admin_can_create_policy(self):
        response = self.client.post("/v1/policies/", data=self.valid, format="json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["agent"], str(self.agent.id))
        self.assertEqual(body["organization"], str(self.organization.id))
        self.assertEqual(body["currency"], "USD")

    def test_new_policy_receives_next_version(self):
        response = self.client.post("/v1/policies/", data=self.valid, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["version"], self.existing_policy.version + 1)
        new = Policy.objects.filter(agent=self.agent).order_by("-version").first()
        self.assertEqual(new.version, 2)

    def test_first_policy_for_agent_starts_at_version_1(self):
        fresh_agent, _ = Agent.create_with_key("fresh", self.organization)
        payload = {**self.valid, "agent": str(fresh_agent.id)}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["version"], 1)

    def test_existing_versions_remain_unchanged(self):
        version_before = self.existing_policy.version
        cap_before = self.existing_policy.per_transaction_cap_minor
        rule_count_before = self.existing_policy.merchant_rules.count()
        self.client.post("/v1/policies/", data=self.valid, format="json")
        self.existing_policy.refresh_from_db()
        self.assertEqual(self.existing_policy.version, version_before)
        self.assertEqual(self.existing_policy.per_transaction_cap_minor, cap_before)
        self.assertEqual(self.existing_policy.merchant_rules.count(), rule_count_before)

    def test_merchant_rules_are_normalized_and_persisted(self):
        payload = {
            **self.valid,
            "merchant_rules": [
                {"merchant_ref": "HTTPS://WWW.ACME.COM/checkout", "kind": "allow", "note": "vendor"},
                {"merchant_ref": "  Evil.com  ", "kind": "block"},
            ],
        }
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 201)
        rules = response.json()["merchant_rules"]
        refs = {r["merchant_ref"] for r in rules}
        self.assertEqual(refs, {"acme.com", "evil.com"})
        self.assertEqual(Policy.objects.get(version=2).merchant_rules.count(), 2)

    def test_defaults_applied_when_money_omitted(self):
        payload = {k: v for k, v in self.valid.items() if k not in
                   {"per_transaction_cap", "approval_threshold", "daily_budget",
                    "weekly_budget", "monthly_budget", "merchant_window_cap", "merchant_rules"}}
        payload["merchant_rules"] = []
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["per_transaction_cap_minor"], 10_000)
        self.assertEqual(body["approval_threshold_minor"], 5_000)
        self.assertEqual(body["currency"], "USD")

    def test_currency_aware_minor_conversion(self):
        payload = {**self.valid, "currency": "JPY", "per_transaction_cap": "5000",
                   "approval_threshold": "1000", "merchant_rules": []}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["per_transaction_cap_minor"], 5000)
        self.assertEqual(response.json()["currency"], "JPY")

    def test_amounts_stored_as_integers_no_floats(self):
        self.client.post("/v1/policies/", data=self.valid, format="json")
        policy = Policy.objects.get(version=2)
        self.assertIsInstance(policy.per_transaction_cap_minor, int)
        self.assertEqual(policy.per_transaction_cap_minor, 10_000)


class PolicyCreateValidationTests(PolicyCreateTestBase):
    def test_negative_money_rejected(self):
        payload = {**self.valid, "per_transaction_cap": "-10.00"}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_non_numeric_money_rejected(self):
        payload = {**self.valid, "daily_budget": "not-a-number"}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_excessive_precision_rejected(self):
        payload = {**self.valid, "weekly_budget": "1000.000"}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_threshold_exceeds_cap_rejected(self):
        payload = {**self.valid, "per_transaction_cap": "100.00", "approval_threshold": "150.00"}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_invalid_currency_rejected(self):
        payload = {**self.valid, "currency": "US"}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_unknown_field_rejected(self):
        payload = {**self.valid, "evil": 1}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_merchant_rule_unknown_field_rejected(self):
        payload = {**self.valid, "merchant_rules": [{"merchant_ref": "acme.com", "kind": "allow", "evil": 1}]}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_conflicting_merchant_rules_rejected(self):
        payload = {**self.valid, "merchant_rules": [
            {"merchant_ref": "acme.com", "kind": "allow"},
            {"merchant_ref": "https://acme.com", "kind": "block"},
        ]}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_duplicate_merchant_rules_rejected(self):
        payload = {**self.valid, "merchant_rules": [
            {"merchant_ref": "acme.com", "kind": "allow"},
            {"merchant_ref": "ACME.com", "kind": "allow"},
        ]}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_invalid_merchant_kind_rejected(self):
        payload = {**self.valid, "merchant_rules": [{"merchant_ref": "acme.com", "kind": "mirror"}]}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)


class PolicyCreatePermissionTests(PolicyCreateTestBase):
    def test_non_admin_member_is_rejected(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post("/v1/policies/", data=self.valid, format="json")
        self.assertEqual(response.status_code, 403)

    def test_non_member_is_rejected(self):
        outsider = User.objects.create_user("outsider")
        self.client.force_authenticate(user=outsider)
        response = self.client.post("/v1/policies/", data=self.valid, format="json")
        self.assertEqual(response.status_code, 403)

    def test_anonymous_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.post("/v1/policies/", data=self.valid, format="json")
        self.assertEqual(response.status_code, 401)

    def test_foreign_organization_agent_is_rejected(self):
        payload = {**self.valid, "agent": str(self.other_agent.id)}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Policy.objects.filter(agent=self.other_agent).exists())

    def test_foreign_admin_cannot_access_foreign_agent(self):
        self.client.force_authenticate(user=self.other_admin)
        payload = {**self.valid, "agent": str(self.agent.id)}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Policy.objects.filter(agent=self.agent, version=2).exists())

    def test_agent_api_key_cannot_authenticate_dashboard_creation(self):
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        response = self.client.post("/v1/policies/", data=self.valid, format="json")
        self.assertEqual(response.status_code, 401)


class PolicyCreateAuditTests(PolicyCreateTestBase):
    def _policy_events(self):
        return AuditEvent.objects.filter(event_type=AuditEvent.EventType.POLICY_CHANGED)

    def test_audit_event_written_on_success(self):
        self.client.post("/v1/policies/", data=self.valid, format="json")
        event = self._policy_events().get()
        self.assertEqual(event.actor_type, AuditEvent.ActorType.USER)
        self.assertEqual(event.actor_id, str(self.admin.id))
        self.assertEqual(event.agent_id, self.agent.id)
        self.assertEqual(event.payload["agent_id"], str(self.agent.id))
        self.assertEqual(event.payload["action"], "created")
        self.assertEqual(event.payload["version"], 2)
        self.assertEqual(event.payload["name"], "Restrictive policy")

    def test_failed_creation_leaves_no_partial_rows(self):
        before_policies = Policy.objects.count()
        before_rules = MerchantRule.objects.count()
        before_events = self._policy_events().count()
        payload = {**self.valid, "per_transaction_cap": "-5.00"}
        response = self.client.post("/v1/policies/", data=payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Policy.objects.count(), before_policies)
        self.assertEqual(MerchantRule.objects.count(), before_rules)
        self.assertEqual(self._policy_events().count(), before_events)

    def test_audit_failure_rolls_back_policy_and_rules(self):
        original = AuditEvent.record.__func__

        def failing_record(cls, event_type, **kwargs):
            if event_type == cls.EventType.POLICY_CHANGED:
                raise RuntimeError("simulated audit failure")
            return original(cls, event_type, **kwargs)

        self.client.raise_request_exception = False
        with mock.patch.object(AuditEvent, "record", classmethod(failing_record)):
            response = self.client.post("/v1/policies/", data=self.valid, format="json")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Policy.objects.filter(version=2).exists())
        self.assertEqual(MerchantRule.objects.filter(policy__version=2).count(), 0)
        self.assertEqual(self._policy_events().count(), 0)


@skipUnless(connection.vendor == "postgresql", "row locking is exercised against PostgreSQL")
class PolicyCreateLockTests(PostgresTransactionTestCase):
    """Concurrent creators must not produce duplicate policy versions."""

    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        self.admin = User.objects.create_user("writer")
        OrgMembership.objects.create(
            user=self.admin, organization=self.organization, role=OrgMembership.Role.ADMIN
        )
        serializer = PolicyCreateSerializer(data=_valid_payload(self.agent.id))
        serializer.is_valid(raise_exception=True)
        self.base_validated = serializer.validated_data

    def worker(self, _):
        close_old_connections()
        try:
            policy = create_policy_version(user=self.admin, validated=self.base_validated)
            return policy.version
        except PolicyConflictError:
            return "conflict"
        finally:
            close_old_connections()

    def test_concurrent_creations_produce_unique_versions(self):
        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(self.worker, range(10)))

        self.assertNotIn("conflict", outcomes)
        versions = [o for o in outcomes if isinstance(o, int)]
        self.assertEqual(len(versions), 10)
        self.assertEqual(sorted(versions), list(range(1, 11)))
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type=AuditEvent.EventType.POLICY_CHANGED
            ).count(),
            10,
        )
