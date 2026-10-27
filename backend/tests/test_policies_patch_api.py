from concurrent.futures import ThreadPoolExecutor
from unittest import mock, skipUnless

from django.db import close_old_connections, connection
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.policies.models import MerchantRule, Policy
from apps.policies.serializers import PolicyUpdateSerializer
from apps.policies.services import PolicyConflictError, create_policy_update
from tests.base import PostgresTransactionTestCase


class PolicyPatchTestBase(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, self.raw_key = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent, weekly_budget_minor=123_400)
        MerchantRule.objects.create(
            policy=self.policy, merchant_ref="acme.com", kind=MerchantRule.Kind.ALLOW
        )
        MerchantRule.objects.create(
            policy=self.policy, merchant_ref="evil.com", kind=MerchantRule.Kind.BLOCK
        )

        self.admin = User.objects.create_user("admin")
        OrgMembership.objects.create(
            user=self.admin, organization=self.organization, role=OrgMembership.Role.ADMIN
        )

        self.viewer = User.objects.create_user("viewer")
        OrgMembership.objects.create(
            user=self.viewer, organization=self.organization, role=OrgMembership.Role.VIEWER
        )

        self.other_org = Organization.objects.create(name="other-org")
        self.other_admin = User.objects.create_user("other-admin")
        OrgMembership.objects.create(
            user=self.other_admin, organization=self.other_org, role=OrgMembership.Role.ADMIN
        )
        self.other_agent, _ = Agent.create_with_key("foreign-agent", self.other_org)

        self.client.force_authenticate(user=self.admin)
        self.url = f"/v1/policies/{self.policy.id}/"

    def _payload(self, **overrides):
        payload = {
            "expected_version": 1,
            "daily_budget": "750.00",
            "approval_threshold": "25.00",
        }
        payload.update(overrides)
        return payload

    def _latest_url(self):
        latest = Policy.objects.filter(agent=self.agent).order_by("-version").first()
        return f"/v1/policies/{latest.id}/"

    def _policy_events(self):
        return AuditEvent.objects.filter(event_type=AuditEvent.EventType.POLICY_CHANGED, agent=self.agent)


class PolicyDetailGetTests(PolicyPatchTestBase):
    def test_member_can_get_policy_detail(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], str(self.policy.id))
        self.assertEqual(body["version"], self.policy.version)
        self.assertEqual(body["weekly_budget_minor"], 123_400)
        self.assertEqual(body["agent_name"], self.agent.name)
        refs = {r["merchant_ref"] for r in body["merchant_rules"]}
        self.assertEqual(refs, {"acme.com", "evil.com"})

    def test_anonymous_get_returns_401(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_foreign_organization_get_returns_404(self):
        self.client.force_authenticate(user=self.other_admin)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_non_member_get_returns_403(self):
        outsider = User.objects.create_user("outsider")
        self.client.force_authenticate(user=outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class PolicyPatchPermissionTests(PolicyPatchTestBase):
    def test_admin_can_patch_latest_policy(self):
        response = self.client.patch(self.url, data=self._payload(), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], 2)

    def test_non_admin_patch_is_forbidden(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.patch(self.url, data=self._payload(), format="json")
        self.assertEqual(response.status_code, 403)

    def test_anonymous_patch_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.patch(self.url, data=self._payload(), format="json")
        self.assertEqual(response.status_code, 401)

    def test_foreign_organization_patch_returns_404(self):
        self.client.force_authenticate(user=self.other_admin)
        response = self.client.patch(self.url, data=self._payload(), format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Policy.objects.filter(agent=self.agent, version=2).exists())

    def test_agent_api_key_cannot_authenticate_get_or_patch(self):
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(
            self.client.patch(self.url, data=self._payload(), format="json").status_code, 401
        )


class PolicyPatchSuccessTests(PolicyPatchTestBase):
    def test_patch_creates_new_id_and_increments_version(self):
        response = self.client.patch(self.url, data=self._payload(), format="json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotEqual(body["id"], str(self.policy.id))
        self.assertEqual(body["version"], self.policy.version + 1)
        self.assertEqual(Policy.objects.filter(agent=self.agent).count(), 2)

    def test_original_policy_and_rules_remain_unchanged(self):
        cap_before = self.policy.per_transaction_cap_minor
        daily_before = self.policy.daily_budget_minor
        rules_before = list(
            self.policy.merchant_rules.order_by("merchant_ref").values_list("merchant_ref", "kind", "note")
        )
        response = self.client.patch(self.url, data=self._payload(), format="json")
        self.assertEqual(response.status_code, 200)

        self.policy.refresh_from_db()
        self.assertEqual(self.policy.per_transaction_cap_minor, cap_before)
        self.assertEqual(self.policy.daily_budget_minor, daily_before)
        rules_after = list(
            self.policy.merchant_rules.order_by("merchant_ref").values_list("merchant_ref", "kind", "note")
        )
        self.assertEqual(rules_after, rules_before)

    def test_omitted_fields_inherit_prior_values(self):
        response = self.client.patch(
            self.url, data={"expected_version": 1, "daily_budget": "750.00"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        new = Policy.objects.get(version=2)
        self.assertEqual(new.weekly_budget_minor, 123_400)
        self.assertEqual(new.per_transaction_cap_minor, self.policy.per_transaction_cap_minor)
        self.assertEqual(new.monthly_budget_minor, self.policy.monthly_budget_minor)
        self.assertEqual(new.merchant_mode, self.policy.merchant_mode)
        self.assertEqual(new.velocity_window_seconds, self.policy.velocity_window_seconds)
        self.assertEqual(new.timezone, self.policy.timezone)
        self.assertEqual(new.daily_budget_minor, 75_000)
        self.assertEqual(new.merchant_rules.count(), 2)

    def test_monetary_changes_use_correct_minor_storage(self):
        response = self.client.patch(
            self.url,
            data={"expected_version": 1, "daily_budget": "750.00", "per_transaction_cap": "120.50"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        new = Policy.objects.get(version=2)
        self.assertEqual(new.daily_budget_minor, 75_000)
        self.assertEqual(new.per_transaction_cap_minor, 12_050)
        self.assertIsInstance(new.daily_budget_minor, int)
        self.assertEqual(response.json()["daily_budget_minor"], 75_000)

    def test_supplied_merchant_rules_replace_the_previous_set(self):
        payload = {
            "expected_version": 1,
            "merchant_rules": [
                {"merchant_ref": "newvendor.com", "kind": "allow", "note": "Primary vendor"},
                {"merchant_ref": "evil.com", "kind": "block"},
            ],
        }
        response = self.client.patch(self.url, data=payload, format="json")
        self.assertEqual(response.status_code, 200)
        new = Policy.objects.get(version=2)
        self.assertEqual(new.merchant_rules.count(), 2)
        self.assertFalse(new.merchant_rules.filter(merchant_ref="acme.com").exists())
        self.assertTrue(new.merchant_rules.filter(merchant_ref="newvendor.com", kind="allow").exists())
        self.assertTrue(new.merchant_rules.filter(merchant_ref="evil.com", kind="block").exists())
        new_rules = [
            (r.merchant_ref, r.kind, r.note)
            for r in self.policy.merchant_rules.order_by("merchant_ref")
        ]
        self.assertEqual(new_rules, [("acme.com", MerchantRule.Kind.ALLOW, ""), ("evil.com", MerchantRule.Kind.BLOCK, "")])


class PolicyPatchValidationTests(PolicyPatchTestBase):
    def test_invalid_money_returns_400(self):
        response = self.client.patch(
            self.url, data=self._payload(daily_budget="not-a-number"), format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_merchant_rule_unknown_field_returns_400(self):
        response = self.client.patch(
            self.url,
            data=self._payload(merchant_rules=[{"merchant_ref": "acme.com", "kind": "allow", "evil": 1}]),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_field_returns_400(self):
        response = self.client.patch(self.url, data=self._payload(evil=1), format="json")
        self.assertEqual(response.status_code, 400)

    def test_missing_expected_version_returns_400(self):
        response = self.client.patch(self.url, data={"daily_budget": "750.00"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_conflicting_merchant_rules_return_400(self):
        response = self.client.patch(
            self.url,
            data=self._payload(
                merchant_rules=[
                    {"merchant_ref": "acme.com", "kind": "allow"},
                    {"merchant_ref": "https://acme.com", "kind": "block"},
                ]
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_inherited_threshold_exceeds_cap_returns_400(self):
        # per_transaction_cap inherited as 10_000 minor; threshold above it is invalid.
        response = self.client.patch(
            self.url, data={"expected_version": 1, "approval_threshold": "500.00"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Policy.objects.filter(agent=self.agent, version=2).exists())


class PolicyPatchConcurrencyTests(PolicyPatchTestBase):
    def test_stale_expected_version_returns_409(self):
        self.client.patch(self.url, data=self._payload(), format="json")
        v2_url = self._latest_url()
        response = self.client.patch(v2_url, data=self._payload(expected_version=1), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Policy.objects.filter(agent=self.agent).count(), 2)

    def test_patch_targeting_older_version_returns_409(self):
        self.client.patch(self.url, data=self._payload(), format="json")
        response = self.client.patch(self.url, data=self._payload(expected_version=2), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Policy.objects.filter(agent=self.agent).count(), 2)


class PolicyPatchAuditTests(PolicyPatchTestBase):
    def test_patch_records_policy_changed(self):
        response = self.client.patch(self.url, data=self._payload(), format="json")
        self.assertEqual(response.status_code, 200)
        event = self._policy_events().last()
        self.assertEqual(event.event_type, AuditEvent.EventType.POLICY_CHANGED)
        self.assertEqual(event.actor_type, AuditEvent.ActorType.USER)
        self.assertEqual(event.actor_id, str(self.admin.id))
        self.assertEqual(event.payload["action"], "updated")
        self.assertEqual(event.payload["old_version"], 1)
        self.assertEqual(event.payload["new_version"], 2)
        self.assertIn("daily_budget", event.payload["fields_changed"])

    def test_audit_event_contains_no_sensitive_data(self):
        self.client.patch(self.url, data=self._payload(), format="json")
        event = self._policy_events().last()
        serialized = str(event.__dict__)
        self.assertNotIn(str(self.raw_key), serialized)
        self.assertNotIn("key_hash", serialized)

    def test_audit_failure_rolls_back_new_version_and_rules(self):
        original = AuditEvent.record.__func__

        def failing_record(cls, event_type, **kwargs):
            if event_type == cls.EventType.POLICY_CHANGED:
                raise RuntimeError("simulated audit failure")
            return original(cls, event_type, **kwargs)

        self.client.raise_request_exception = False
        with mock.patch.object(AuditEvent, "record", classmethod(failing_record)):
            response = self.client.patch(self.url, data=self._payload(), format="json")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Policy.objects.filter(version=2).exists())
        self.assertEqual(MerchantRule.objects.filter(policy__version=2).count(), 0)
        self.assertEqual(self._policy_events().count(), 0)


@skipUnless(connection.vendor == "postgresql", "row locking is exercised against PostgreSQL")
class PolicyPatchLockTests(PostgresTransactionTestCase):
    """Concurrent PATCH requests on the same agent must serialize and never
    produce duplicate (agent, version) rows."""

    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)
        MerchantRule.objects.create(
            policy=self.policy, merchant_ref="acme.com", kind=MerchantRule.Kind.ALLOW
        )
        self.admin = User.objects.create_user("writer")
        OrgMembership.objects.create(
            user=self.admin, organization=self.organization, role=OrgMembership.Role.ADMIN
        )
        self.payload = {"expected_version": 1, "daily_budget": "750.00"}

    def worker(self, _):
        close_old_connections()
        try:
            serializer = PolicyUpdateSerializer(data=self.payload)
            serializer.is_valid(raise_exception=True)
            create_policy_update(
                user=self.admin, policy_id=self.policy.id, validated=serializer.validated_data
            )
            return "ok"
        except PolicyConflictError:
            return "conflict"
        finally:
            close_old_connections()

    def test_concurrent_patches_never_duplicate_versions(self):
        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(self.worker, range(10)))

        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count("conflict"), 9)
        versions = list(Policy.objects.filter(agent=self.agent).values_list("version", flat=True))
        self.assertEqual(sorted(versions), [1, 2])
        self.assertEqual(Policy.objects.filter(agent=self.agent, version=2).count(), 1)
        self.assertEqual(
            AuditEvent.objects.filter(event_type=AuditEvent.EventType.POLICY_CHANGED).count(), 1
        )
