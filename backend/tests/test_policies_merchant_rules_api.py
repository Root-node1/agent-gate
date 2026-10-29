from concurrent.futures import ThreadPoolExecutor
from unittest import mock, skipUnless

from django.db import close_old_connections, connection
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.policies.models import MerchantRule, Policy
from apps.policies.serializers import MerchantRuleCreateSerializer
from apps.policies.services import PolicyConflictError, add_merchant_rule
from tests.base import PostgresTransactionTestCase, force_mfa


class MerchantRuleTestBase(APITestCase):
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
        self.add_url = f"/v1/policies/{self.policy.id}/merchant-rules/"

    def _rule_ids(self, policy):
        return list(policy.merchant_rules.order_by("merchant_ref").values_list("id", flat=True))

    def _policy_events(self):
        return AuditEvent.objects.filter(
            event_type=AuditEvent.EventType.POLICY_CHANGED, agent=self.agent
        )

    def _latest_policy(self):
        return Policy.objects.filter(agent=self.agent).order_by("-version").first()


# ---------------------------------------------------------------------------
# POST success
# ---------------------------------------------------------------------------


class MerchantRuleCreateSuccessTests(MerchantRuleTestBase):
    def test_admin_can_add_merchant_rule(self):
        payload = {
            "expected_version": 1,
            "merchant_ref": "newvendor.com",
            "kind": "allow",
            "note": "Primary vendor",
        }
        response = self.client.post(self.add_url, data=payload, format="json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["version"], 2)
        self.assertNotEqual(body["id"], str(self.policy.id))
        refs = {r["merchant_ref"] for r in body["merchant_rules"]}
        self.assertEqual(refs, {"acme.com", "evil.com", "newvendor.com"})
        kinds = {r["merchant_ref"]: r["kind"] for r in body["merchant_rules"]}
        self.assertEqual(kinds["newvendor.com"], "allow")
        self.assertEqual(kinds["acme.com"], "allow")
        self.assertEqual(kinds["evil.com"], "block")

    def test_add_creates_new_id_and_increments_version(self):
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "block"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        new_id = response.json()["id"]
        new_version = response.json()["version"]
        self.assertNotEqual(new_id, str(self.policy.id))
        self.assertEqual(new_version, self.policy.version + 1)
        self.assertEqual(Policy.objects.filter(agent=self.agent).count(), 2)

    def test_original_policy_and_rules_remain_unchanged(self):
        self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "block"},
            format="json",
        )
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.version, 1)
        self.assertEqual(
            sorted(self.policy.merchant_rules.values_list("merchant_ref", flat=True)),
            ["acme.com", "evil.com"],
        )

    def test_existing_rules_are_inherited(self):
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        new = self._latest_policy()
        self.assertEqual(new.merchant_rules.count(), 3)
        self.assertTrue(new.merchant_rules.filter(merchant_ref="acme.com", kind="allow").exists())
        self.assertTrue(new.merchant_rules.filter(merchant_ref="evil.com", kind="block").exists())
        self.assertTrue(new.merchant_rules.filter(merchant_ref="new.com", kind="allow").exists())

    def test_merchant_normalization_on_add(self):
        response = self.client.post(
            self.add_url,
            data={
                "expected_version": 1,
                "merchant_ref": "HTTPS://WWW.ACME.COM/checkout",
                "kind": "block",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["detail"], "Merchant 'acme.com' cannot be both allowed and blocked.")

    def test_note_optional_on_add(self):
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "note.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        new = self._latest_policy()
        rule = new.merchant_rules.get(merchant_ref="note.com")
        self.assertEqual(rule.note, "")

    def test_note_is_preserved_on_add(self):
        response = self.client.post(
            self.add_url,
            data={
                "expected_version": 1,
                "merchant_ref": "note.com",
                "kind": "block",
                "note": "Blocked for fraud",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        new = self._latest_policy()
        rule = new.merchant_rules.get(merchant_ref="note.com")
        self.assertEqual(rule.note, "Blocked for fraud")


# ---------------------------------------------------------------------------
# POST validation
# ---------------------------------------------------------------------------


class MerchantRuleCreateValidationTests(MerchantRuleTestBase):
    def test_duplicate_merchant_returns_400(self):
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "acme.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Policy.objects.filter(agent=self.agent, version=2).count(), 0)

    def test_conflicting_kind_returns_400(self):
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "acme.com", "kind": "block"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Policy.objects.filter(agent=self.agent, version=2).count(), 0)

    def test_invalid_kind_returns_400(self):
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "mirror"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_merchant_ref_returns_400(self):
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_field_returns_400(self):
        response = self.client.post(
            self.add_url,
            data={
                "expected_version": 1,
                "merchant_ref": "new.com",
                "kind": "allow",
                "evil": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_expected_version_returns_400(self):
        response = self.client.post(
            self.add_url,
            data={"merchant_ref": "new.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# POST permissions
# ---------------------------------------------------------------------------


class MerchantRuleCreatePermissionTests(MerchantRuleTestBase):
    def test_non_admin_member_returns_403(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Policy.objects.filter(agent=self.agent, version=2).count(), 0)

    def test_anonymous_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_agent_api_key_rejected(self):
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_foreign_organization_policy_returns_404(self):
        self.client.force_authenticate(user=self.other_admin)
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Policy.objects.filter(agent=self.agent, version=2).count(), 0)

    def test_foreign_admin_cannot_add_to_foreign_policy(self):
        self.client.force_authenticate(user=self.other_admin)
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Policy.objects.filter(agent=self.agent, version=2).count(), 0)


# ---------------------------------------------------------------------------
# POST concurrency
# ---------------------------------------------------------------------------


class MerchantRuleCreateConcurrencyTests(MerchantRuleTestBase):
    def test_stale_expected_version_returns_409(self):
        self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "first.com", "kind": "allow"},
            format="json",
        )
        # Version is now 2; sending expected_version=1 is stale.
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "second.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Policy.objects.filter(agent=self.agent).count(), 2)

    def test_add_targeting_older_version_returns_409(self):
        newer = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "first.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(newer.status_code, 201)
        # The original policy URL is version 1, which is no longer the latest.
        response = self.client.post(
            self.add_url,
            data={"expected_version": 2, "merchant_ref": "second.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)


# ---------------------------------------------------------------------------
# DELETE success
# ---------------------------------------------------------------------------


class MerchantRuleDeleteSuccessTests(MerchantRuleTestBase):
    def setUp(self):
        super().setUp()
        self.rule_acme = self.policy.merchant_rules.get(merchant_ref="acme.com")
        self.delete_url = f"/v1/policies/{self.policy.id}/merchant-rules/{self.rule_acme.id}/"

    def _delete(self, version=1):
        return self.client.delete(
            self.delete_url,
            HTTP_IF_MATCH=str(version),
        )

    def test_admin_can_remove_merchant_rule(self):
        response = self._delete()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], 2)
        refs = {r["merchant_ref"] for r in body["merchant_rules"]}
        self.assertEqual(refs, {"evil.com"})

    def test_remove_creates_new_id_and_increments_version(self):
        response = self._delete()
        self.assertEqual(response.status_code, 200)
        new_id = response.json()["id"]
        new_version = response.json()["version"]
        self.assertNotEqual(new_id, str(self.policy.id))
        self.assertEqual(new_version, self.policy.version + 1)
        self.assertEqual(Policy.objects.filter(agent=self.agent).count(), 2)

    def test_original_rule_remains_unchanged(self):
        before = self.rule_acme
        self._delete()
        before.refresh_from_db()
        self.assertEqual(before.merchant_ref, "acme.com")
        self.assertEqual(before.kind, MerchantRule.Kind.ALLOW)

    def test_original_policy_unchanged(self):
        self._delete()
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.version, 1)
        self.assertEqual(self.policy.merchant_rules.count(), 2)

    def test_existing_rule_inherited_after_removal(self):
        response = self._delete()
        self.assertEqual(response.status_code, 200)
        new = self._latest_policy()
        self.assertEqual(new.merchant_rules.count(), 1)
        self.assertTrue(new.merchant_rules.filter(merchant_ref="evil.com", kind="block").exists())
        self.assertFalse(new.merchant_rules.filter(merchant_ref="acme.com").exists())

    def test_remaining_rules_preserve_kind_and_note(self):
        # Add a rule with a note, then remove acme.com
        self.client.post(
            self.add_url,
            data={
                "expected_version": 1,
                "merchant_ref": "note.com",
                "kind": "block",
                "note": "blocked",
            },
            format="json",
        )
        v2 = self._latest_policy()
        evil = v2.merchant_rules.get(merchant_ref="evil.com")
        note = v2.merchant_rules.get(merchant_ref="note.com")
        self.assertEqual(note.note, "blocked")

        delete_url = f"/v1/policies/{v2.id}/merchant-rules/{evil.id}/"
        response = self.client.delete(delete_url, HTTP_IF_MATCH="2")
        self.assertEqual(response.status_code, 200)
        v3 = self._latest_policy()
        note_v3 = v3.merchant_rules.get(merchant_ref="note.com")
        self.assertEqual(note_v3.note, "blocked")
        self.assertEqual(v3.merchant_rules.count(), 2)


# ---------------------------------------------------------------------------
# DELETE validation and concurrency
# ---------------------------------------------------------------------------


class MerchantRuleDeleteValidationTests(MerchantRuleTestBase):
    def setUp(self):
        super().setUp()
        self.rule_acme = self.policy.merchant_rules.get(merchant_ref="acme.com")
        self.delete_url = f"/v1/policies/{self.policy.id}/merchant-rules/{self.rule_acme.id}/"

    def test_missing_if_match_returns_400(self):
        response = self.client.delete(self.delete_url)
        self.assertEqual(response.status_code, 400)

    def test_invalid_if_match_returns_400(self):
        response = self.client.delete(self.delete_url, HTTP_IF_MATCH="not-a-number")
        self.assertEqual(response.status_code, 400)

    def test_unknown_rule_id_returns_404(self):
        fake_rule_id = "0" * 32
        response = self.client.delete(
            f"/v1/policies/{self.policy.id}/merchant-rules/{fake_rule_id}/",
            HTTP_IF_MATCH="1",
        )
        self.assertEqual(response.status_code, 404)

    def test_stale_expected_version_returns_409(self):
        self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "first.com", "kind": "allow"},
            format="json",
        )
        # Latest is now version 2; delete with expected_version 1 is stale.
        response = self.client.delete(self.delete_url, HTTP_IF_MATCH="1")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Policy.objects.filter(agent=self.agent).count(), 2)

    def test_delete_targeting_old_version_returns_409(self):
        # Create version 2
        self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "first.com", "kind": "allow"},
            format="json",
        )
        v2 = self._latest_policy()
        v1_rule = self.policy.merchant_rules.get(merchant_ref="acme.com")
        # Try to delete the v1 rule via the old URL — the old policy no longer
        # matches expected_version 2, so create_policy_update raises 409.
        old_url = f"/v1/policies/{self.policy.id}/merchant-rules/{v1_rule.id}/"
        response = self.client.delete(old_url, HTTP_IF_MATCH="2")
        self.assertEqual(response.status_code, 409)
        # The rule still exists on the latest version.
        self.assertTrue(v2.merchant_rules.filter(merchant_ref="acme.com").exists())

    def test_remove_from_old_policy_version_404(self):
        # The rule_acme was created on v1.  After PATCHing to v2, that specific
        # rule row still exists (it's on policy v1).  DELETEing via a policy ID
        # that is no longer the latest produces 409 (stale), not success.
        self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "first.com", "kind": "allow"},
            format="json",
        )
        response = self.client.delete(self.delete_url, HTTP_IF_MATCH="1")
        self.assertEqual(response.status_code, 409)


# ---------------------------------------------------------------------------
# DELETE permissions
# ---------------------------------------------------------------------------


class MerchantRuleDeletePermissionTests(MerchantRuleTestBase):
    def setUp(self):
        super().setUp()
        self.rule_acme = self.policy.merchant_rules.get(merchant_ref="acme.com")
        self.delete_url = f"/v1/policies/{self.policy.id}/merchant-rules/{self.rule_acme.id}/"

    def test_non_admin_returns_403(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.delete(self.delete_url, HTTP_IF_MATCH="1")
        self.assertEqual(response.status_code, 403)

    def test_anonymous_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.delete(self.delete_url, HTTP_IF_MATCH="1")
        self.assertEqual(response.status_code, 401)

    def test_agent_api_key_rejected(self):
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        response = self.client.delete(self.delete_url, HTTP_IF_MATCH="1")
        self.assertEqual(response.status_code, 401)

    def test_foreign_organization_delete_returns_404(self):
        self.client.force_authenticate(user=self.other_admin)
        delete_url = f"/v1/policies/{self.policy.id}/merchant-rules/{self.rule_acme.id}/"
        response = self.client.delete(delete_url, HTTP_IF_MATCH="1")
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class MerchantRuleAuditTests(MerchantRuleTestBase):
    def setUp(self):
        super().setUp()
        self.rule_acme = self.policy.merchant_rules.get(merchant_ref="acme.com")
        self.rule_id = str(self.rule_acme.id)

    def test_add_records_audit_event(self):
        response = self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "allow"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        event = self._policy_events().get()
        self.assertEqual(event.event_type, AuditEvent.EventType.POLICY_CHANGED)
        self.assertEqual(event.actor_type, AuditEvent.ActorType.USER)
        self.assertEqual(event.actor_id, str(self.admin.id))
        self.assertEqual(event.payload["action"], "merchant_rule_added")
        self.assertEqual(event.payload["merchant_ref"], "new.com")
        self.assertEqual(event.payload["kind"], "allow")
        self.assertEqual(event.payload["old_version"], 1)
        self.assertEqual(event.payload["new_version"], 2)

    def test_remove_records_audit_event(self):
        url = f"/v1/policies/{self.policy.id}/merchant-rules/{self.rule_id}/"
        response = self.client.delete(url, HTTP_IF_MATCH="1")
        self.assertEqual(response.status_code, 200)
        event = self._policy_events().get()
        self.assertEqual(event.payload["action"], "merchant_rule_removed")
        self.assertEqual(event.payload["merchant_ref"], "acme.com")
        self.assertEqual(event.payload["old_version"], 1)
        self.assertEqual(event.payload["new_version"], 2)

    def test_add_audit_failure_rolls_back(self):
        original = AuditEvent.record.__func__

        def failing_record(cls, event_type, **kwargs):
            if event_type == cls.EventType.POLICY_CHANGED:
                raise RuntimeError("simulated audit failure")
            return original(cls, event_type, **kwargs)

        self.client.raise_request_exception = False
        with mock.patch.object(AuditEvent, "record", classmethod(failing_record)):
            response = self.client.post(
                self.add_url,
                data={"expected_version": 1, "merchant_ref": "new.com", "kind": "allow"},
                format="json",
            )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Policy.objects.filter(version=2).exists())
        self.assertEqual(MerchantRule.objects.filter(policy__version=2).count(), 0)
        self.assertEqual(self._policy_events().count(), 0)

    def test_remove_audit_failure_rolls_back(self):
        original = AuditEvent.record.__func__

        def failing_record(cls, event_type, **kwargs):
            if event_type == cls.EventType.POLICY_CHANGED:
                raise RuntimeError("simulated audit failure")
            return original(cls, event_type, **kwargs)

        url = f"/v1/policies/{self.policy.id}/merchant-rules/{self.rule_id}/"
        self.client.raise_request_exception = False
        with mock.patch.object(AuditEvent, "record", classmethod(failing_record)):
            response = self.client.delete(url, HTTP_IF_MATCH="1")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Policy.objects.filter(version=2).exists())
        self.assertEqual(MerchantRule.objects.filter(policy__version=2).count(), 0)
        self.assertEqual(self._policy_events().count(), 0)

    def test_audit_contains_no_sensitive_data(self):
        self.client.post(
            self.add_url,
            data={"expected_version": 1, "merchant_ref": "new.com", "kind": "allow"},
            format="json",
        )
        event = self._policy_events().get()
        serialized = str(event.__dict__)
        self.assertNotIn(self.raw_key, serialized)
        self.assertNotIn("key_hash", serialized)


# ---------------------------------------------------------------------------
# PostgreSQL concurrency
# ---------------------------------------------------------------------------


@skipUnless(connection.vendor == "postgresql", "row locking is exercised against PostgreSQL")
class MerchantRuleConcurrencyTests(PostgresTransactionTestCase):
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

    def _make_serializer(self):
        from apps.policies.serializers import MerchantRuleCreateSerializer

        serializer = MerchantRuleCreateSerializer(data=self._payload())
        serializer.is_valid(raise_exception=True)
        return serializer

    def _payload(self, **overrides):
        payload = {
            "expected_version": 1,
            "merchant_ref": "concurrent.com",
            "kind": "allow",
        }
        payload.update(overrides)
        return payload

    def worker(self, _):
        close_old_connections()
        try:
            serializer = MerchantRuleCreateSerializer(data=self._payload())
            serializer.is_valid(raise_exception=True)
            add_merchant_rule(
                user=self.admin,
                policy_id=self.policy.id,
                validated=serializer.validated_data,
            )
            return "ok"
        except PolicyConflictError:
            return "conflict"
        except Exception:
            return "error"
        finally:
            close_old_connections()

    def test_concurrent_adds_never_duplicate_versions(self):
        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(self.worker, range(10)))

        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count("conflict"), 9)
        versions = list(
            Policy.objects.filter(agent=self.agent).values_list("version", flat=True)
        )
        self.assertEqual(sorted(versions), [1, 2])
        self.assertEqual(Policy.objects.filter(agent=self.agent, version=2).count(), 1)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type=AuditEvent.EventType.POLICY_CHANGED
            ).count(),
            1,
        )
