from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.keys import hash_key
from apps.agents.models import Agent, ApiKey
from apps.audit.models import AuditEvent
from apps.common.money import to_major, to_minor
from apps.payees.models import DestinationType, Payee, fingerprint
from apps.payments.executors import FakeExecutor
from apps.payments.models import WebhookEvent
from apps.policies.models import MerchantRule, Policy
from apps.spend.models import SpendRequest


def make_agent(name="shopper", org_name="default"):
    organization, _ = Organization.objects.get_or_create(name=org_name)
    return Agent.create_with_key(name, organization)


class HealthTests(TestCase):
    def test_health_returns_ok(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_checks_the_database(self):
        response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_legacy_health_alias_still_works(self):
        self.assertEqual(self.client.get("/api/health/").status_code, 200)


class AgentTests(TestCase):
    def test_create_with_key_stores_only_the_hash(self):
        agent, raw_key = make_agent()
        api_key = agent.api_keys.get()
        self.assertTrue(raw_key.startswith("agk_"))
        self.assertEqual(api_key.key_hash, hash_key(raw_key))
        self.assertNotEqual(api_key.key_hash, raw_key)
        self.assertEqual(api_key.prefix, raw_key[:12])

    def test_agent_name_is_unique_per_organization(self):
        make_agent("shopper")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_agent("shopper")

    def test_key_can_be_rotated(self):
        agent, _ = make_agent()
        ApiKey.create_key(agent)
        self.assertEqual(agent.api_keys.count(), 2)


class MoneyTests(TestCase):
    def test_two_decimal_currency_round_trip(self):
        self.assertEqual(to_minor(Decimal("12.34"), "USD"), 1234)
        self.assertEqual(to_major(1234, "USD"), Decimal("12.34"))

    def test_zero_decimal_currency(self):
        self.assertEqual(to_minor(Decimal("1200"), "JPY"), 1200)
        self.assertEqual(to_major(1200, "JPY"), Decimal("1200"))


class PolicyTests(TestCase):
    def test_threshold_cannot_exceed_cap(self):
        agent, _ = make_agent()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Policy.objects.create(
                agent=agent,
                per_transaction_cap_minor=1000,
                approval_threshold_minor=2000,
            )

    def test_currency_is_normalized_and_validated(self):
        agent, _ = make_agent()
        policy = Policy.objects.create(agent=agent, currency="usd")
        self.assertEqual(policy.currency, "USD")
        with self.assertRaises(ValidationError):
            Policy(currency="ZZZ").full_clean()

    def test_negative_money_fails_validation(self):
        agent, _ = make_agent("neg")
        policy = Policy(agent=agent, per_transaction_cap_minor=-1)
        with self.assertRaises(ValidationError):
            policy.full_clean()

    def test_injection_threshold_is_bounded(self):
        agent, _ = make_agent("inj")
        with self.assertRaises(ValidationError):
            Policy(agent=agent, injection_escalate_threshold=101).full_clean()
        policy = Policy.objects.create(agent=agent)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Policy.objects.filter(pk=policy.pk).update(injection_escalate_threshold=101)

    def test_invalid_timezone_is_rejected(self):
        agent, _ = make_agent("tz")
        with self.assertRaises(ValidationError):
            Policy(agent=agent, timezone="Nowhere/Fake").full_clean()
        with self.assertRaises(ValidationError):
            Policy.objects.create(agent=agent, timezone="Nowhere/Fake")

    def test_merchant_unique_per_policy(self):
        agent, _ = make_agent("b")
        policy = Policy.objects.create(agent=agent)
        MerchantRule.objects.create(policy=policy, merchant_ref="acme.com", kind="allow")
        with self.assertRaises(IntegrityError), transaction.atomic():
            MerchantRule.objects.create(policy=policy, merchant_ref="acme.com", kind="block")

    def test_policy_versions_are_unique_per_agent(self):
        agent, _ = make_agent("c")
        Policy.objects.create(agent=agent, version=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Policy.objects.create(agent=agent, version=1)


class PayeeTests(TestCase):
    def test_fingerprint_normalizes_the_destination(self):
        first = fingerprint(DestinationType.PAYPAL_EMAIL, "Seller@Example.com")
        second = fingerprint(DestinationType.PAYPAL_EMAIL, " seller@example.com ")
        self.assertEqual(first, second)

    def test_phone_and_url_normalization(self):
        self.assertEqual(
            fingerprint(DestinationType.PHONE, "+1 (555) 010-9999"),
            fingerprint(DestinationType.PHONE, "15550109999"),
        )
        self.assertEqual(
            fingerprint(DestinationType.URL, "HTTPS://WWW.Shop.Example/checkout/"),
            fingerprint(DestinationType.URL, "https://shop.example/checkout"),
        )

    def test_payee_is_unique_per_merchant(self):
        organization = Organization.objects.create(name="acme")
        Payee.objects.create(
            organization=organization,
            merchant_ref="shop.example",
            destination_type=DestinationType.PAYPAL_EMAIL,
            destination_value="a@example.com",
            destination_fingerprint=fingerprint(DestinationType.PAYPAL_EMAIL, "a@example.com"),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payee.objects.create(
                organization=organization,
                merchant_ref="shop.example",
                destination_type=DestinationType.PAYPAL_EMAIL,
                destination_value="b@example.com",
                destination_fingerprint=fingerprint(DestinationType.PAYPAL_EMAIL, "b@example.com"),
            )


class OrganizationTests(TestCase):
    def test_membership_is_unique_per_user_and_org(self):
        user = User.objects.create_user(username="dash", password="x")
        organization = Organization.objects.create(name="acme")
        OrgMembership.objects.create(user=user, organization=organization, role="admin")
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrgMembership.objects.create(user=user, organization=organization, role="viewer")


class WebhookEventTests(TestCase):
    def test_paypal_event_id_is_unique(self):
        WebhookEvent.objects.create(paypal_event_id="evt_1", event_type="PAYMENT.SALE.COMPLETED")
        with self.assertRaises(IntegrityError), transaction.atomic():
            WebhookEvent.objects.create(paypal_event_id="evt_1", event_type="PAYMENT.SALE.COMPLETED")


class SpendRequestTests(TestCase):
    def setUp(self):
        self.agent, _ = make_agent()
        self.policy = Policy.objects.create(agent=self.agent)

    def make_spend(self, *, save=True, **overrides):
        values = {
            "organization": self.agent.organization,
            "agent": self.agent,
            "policy": self.policy,
            "policy_version": self.policy.version,
            "amount_minor": 1000,
            "currency": "USD",
            "merchant_ref": "acme.com",
            "decision": SpendRequest.Decision.ALLOW,
            "status": SpendRequest.Status.APPROVED,
        }
        values.update(overrides)
        if save:
            return SpendRequest.objects.create(**values)
        return SpendRequest(**values)

    def test_decision_is_immutable(self):
        spend = self.make_spend()
        spend.decision = SpendRequest.Decision.DENY
        with self.assertRaises(ValueError):
            spend.save()

    def test_idempotency_key_is_unique_per_agent(self):
        self.make_spend(idempotency_key="abc")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_spend(idempotency_key="abc")

    def test_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_spend(amount_minor=0)

    def test_negative_amount_fails_validation(self):
        spend = self.make_spend()
        spend.amount_minor = -1
        with self.assertRaises(ValidationError):
            spend.full_clean()

    def test_text_fields_are_bounded(self):
        spend = self.make_spend(save=False, purpose="x" * 2_001)
        with self.assertRaises(ValidationError):
            spend.full_clean()
        spend = self.make_spend(save=False, evidence_excerpt="x" * 4_097)
        with self.assertRaises(ValidationError):
            spend.full_clean()


class AuditEventTests(TestCase):
    def test_record_creates_event(self):
        organization = Organization.objects.create(name="acme")
        event = AuditEvent.record(
            AuditEvent.EventType.DECISION_MADE, organization=organization, detail="hello"
        )
        self.assertEqual(event.payload, {"detail": "hello"})

    def test_cannot_modify_or_delete(self):
        organization = Organization.objects.create(name="acme")
        event = AuditEvent.record(AuditEvent.EventType.DECISION_MADE, organization=organization)
        event.event_type = AuditEvent.EventType.PAYMENT_FAILED
        with self.assertRaises(PermissionError):
            event.save()
        with self.assertRaises(PermissionError):
            event.delete()


class FakeExecutorTests(TestCase):
    def test_modes(self):
        agent, _ = make_agent("exec")
        policy = Policy.objects.create(agent=agent)
        spend = SpendRequest.objects.create(
            organization=agent.organization,
            agent=agent,
            policy=policy,
            policy_version=policy.version,
            amount_minor=500,
            currency="USD",
            merchant_ref="acme.com",
            decision=SpendRequest.Decision.ALLOW,
            status=SpendRequest.Status.APPROVED,
        )
        self.assertEqual(FakeExecutor("succeed").execute(spend).status, "COMPLETED")
        self.assertEqual(FakeExecutor("fail").execute(spend).status, "FAILED")
        self.assertEqual(FakeExecutor("held").execute(spend).status, "HELD")
        with self.assertRaises(TimeoutError):
            FakeExecutor("timeout").execute(spend)
        with self.assertRaises(ValueError):
            FakeExecutor("nonsense")


class AuditProtectionTests(TestCase):
    def test_audit_rows_block_deleting_the_organization(self):
        agent, _ = make_agent()
        AuditEvent.record(AuditEvent.EventType.AGENT_CREATED, organization=agent.organization)
        with self.assertRaises(ProtectedError):
            agent.organization.delete()
