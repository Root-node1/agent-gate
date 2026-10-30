"""INT-13E: CheckoutOrder domain model and durable operation-record tests.

All tests are offline — no PayPal API calls are made.
"""

from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.payments.models import CheckoutOrder
from apps.policies.models import Policy
from apps.spend.models import SpendRequest
from apps.spend.services import counted_spend


def make_organization(name="checkout-org"):
    return Organization.objects.create(name=name)


class CheckoutOrderTests(TestCase):
    def setUp(self):
        self.organization = make_organization()
        self.agent = Agent.objects.create(
            name="checkout-agent", organization=self.organization
        )
        self.policy = Policy.objects.create(agent=self.agent)

    def make_checkout(self, *, save=True, **overrides):
        values = {
            "organization": self.organization,
            "amount_minor": 1000,
            "currency": "USD",
        }
        values.update(overrides)
        if save:
            return CheckoutOrder.objects.create(**values)
        return CheckoutOrder(**values)

    # 1. Valid CheckoutOrder creation
    def test_valid_creation(self):
        checkout = self.make_checkout()
        self.assertEqual(checkout.status, CheckoutOrder.Status.CREATED)
        self.assertEqual(checkout.amount_minor, 1000)
        self.assertEqual(checkout.currency, "USD")
        self.assertEqual(checkout.organization_id, self.organization.id)

    # 2. Invalid amount rejection
    def test_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_checkout(amount_minor=0)

    def test_negative_amount_fails_validation(self):
        checkout = self.make_checkout(save=False, amount_minor=-1)
        with self.assertRaises(ValidationError):
            checkout.full_clean()

    # 3. Invalid currency rejection
    def test_invalid_currency_fails_validation(self):
        checkout = self.make_checkout(save=False, currency="XYZ")
        with self.assertRaises(ValidationError):
            checkout.full_clean()

    def test_currency_is_normalized_on_save(self):
        checkout = self.make_checkout(save=False, currency="usd")
        checkout.save()
        self.assertEqual(checkout.currency, "USD")

    # 4. Unique PayPal order ID
    def test_paypal_order_id_is_unique(self):
        self.make_checkout(paypal_order_id="PAYPAL-ORDER-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_checkout(paypal_order_id="PAYPAL-ORDER-1")

    # 5. Unique PayPal capture ID
    def test_paypal_capture_id_is_unique(self):
        self.make_checkout(paypal_capture_id="PAYPAL-CAPTURE-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_checkout(paypal_capture_id="PAYPAL-CAPTURE-1")

    def test_null_paypal_ids_are_not_unique(self):
        first = self.make_checkout()
        second = self.make_checkout()
        self.assertIsNone(first.paypal_order_id)
        self.assertIsNone(second.paypal_order_id)

    # 6. Financial snapshot immutability
    def test_amount_minor_is_immutable(self):
        checkout = self.make_checkout()
        checkout.amount_minor = 999
        with self.assertRaises(ValueError):
            checkout.save()

    def test_currency_is_immutable(self):
        checkout = self.make_checkout()
        checkout.currency = "EUR"
        with self.assertRaises(ValueError):
            checkout.save()

    def test_organization_is_immutable(self):
        other_org = make_organization("other-org")
        checkout = self.make_checkout()
        checkout.organization_id = other_org.id
        with self.assertRaises(ValueError):
            checkout.save()

    # 7. Valid state transitions
    def test_valid_forward_transitions(self):
        checkout = self.make_checkout()
        checkout.transition_to(CheckoutOrder.Status.PAYER_ACTION_REQUIRED)
        self.assertEqual(checkout.status, CheckoutOrder.Status.PAYER_ACTION_REQUIRED)

        checkout.transition_to(CheckoutOrder.Status.APPROVED)
        self.assertEqual(checkout.status, CheckoutOrder.Status.APPROVED)

        checkout.transition_to(CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertEqual(checkout.status, CheckoutOrder.Status.CAPTURE_PENDING)

        checkout.transition_to(CheckoutOrder.Status.COMPLETED)
        self.assertEqual(checkout.status, CheckoutOrder.Status.COMPLETED)

    def test_valid_decline_from_created(self):
        checkout = self.make_checkout()
        checkout.transition_to(CheckoutOrder.Status.DECLINED)
        self.assertEqual(checkout.status, CheckoutOrder.Status.DECLINED)

    def test_valid_void_from_created(self):
        checkout = self.make_checkout()
        checkout.transition_to(CheckoutOrder.Status.VOIDED)
        self.assertEqual(checkout.status, CheckoutOrder.Status.VOIDED)

    def test_approved_to_voided(self):
        checkout = self.make_checkout()
        checkout.transition_to(CheckoutOrder.Status.PAYER_ACTION_REQUIRED)
        checkout.transition_to(CheckoutOrder.Status.APPROVED)
        checkout.transition_to(CheckoutOrder.Status.VOIDED)
        self.assertEqual(checkout.status, CheckoutOrder.Status.VOIDED)

    # 8. Invalid backward transitions
    def test_cannot_go_backward_from_completed(self):
        checkout = self.make_checkout()
        checkout.transition_to(CheckoutOrder.Status.PAYER_ACTION_REQUIRED)
        checkout.transition_to(CheckoutOrder.Status.APPROVED)
        checkout.transition_to(CheckoutOrder.Status.CAPTURE_PENDING)
        checkout.transition_to(CheckoutOrder.Status.COMPLETED)
        with self.assertRaises(ValueError):
            checkout.transition_to(CheckoutOrder.Status.APPROVED)

    def test_cannot_skip_intermediate_states(self):
        checkout = self.make_checkout()
        with self.assertRaises(ValueError):
            checkout.transition_to(CheckoutOrder.Status.APPROVED)
        with self.assertRaises(ValueError):
            checkout.transition_to(CheckoutOrder.Status.COMPLETED)

    def test_cannot_transition_from_declined(self):
        checkout = self.make_checkout()
        checkout.transition_to(CheckoutOrder.Status.DECLINED)
        with self.assertRaises(ValueError):
            checkout.transition_to(CheckoutOrder.Status.COMPLETED)

    def test_cannot_transition_from_voided(self):
        checkout = self.make_checkout()
        checkout.transition_to(CheckoutOrder.Status.VOIDED)
        with self.assertRaises(ValueError):
            checkout.transition_to(CheckoutOrder.Status.APPROVED)

    def test_direct_status_change_via_save_blocked(self):
        checkout = self.make_checkout()
        checkout.status = CheckoutOrder.Status.COMPLETED
        with self.assertRaises(ValueError):
            checkout.save()

    # 9. Duplicate operation identity rejection
    def test_duplicate_idempotency_key_rejected(self):
        key = uuid4()
        self.make_checkout(idempotency_key=key)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_checkout(idempotency_key=key)

    def test_duplicate_capture_idempotency_key_rejected(self):
        key = uuid4()
        self.make_checkout(capture_idempotency_key=key)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_checkout(capture_idempotency_key=key)

    def test_null_idempotency_keys_are_not_unique(self):
        first = self.make_checkout()
        second = self.make_checkout()
        self.assertIsNone(first.idempotency_key)
        self.assertIsNone(second.idempotency_key)

    # 10. Organization scoping
    def test_checkout_is_scoped_to_organization(self):
        org_a = make_organization("org-a")
        org_b = make_organization("org-b")
        checkout = self.make_checkout(organization=org_a)
        self.assertEqual(checkout.organization_id, org_a.id)
        self.assertNotEqual(checkout.organization_id, org_b.id)
        self.assertIn(checkout, org_a.checkout_orders.all())
        self.assertNotIn(checkout, org_b.checkout_orders.all())

    def test_paypal_order_id_unique_across_organizations(self):
        org_a = make_organization("org-a")
        org_b = make_organization("org-b")
        self.make_checkout(organization=org_a, paypal_order_id="SHARED-ORDER-ID")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_checkout(organization=org_b, paypal_order_id="SHARED-ORDER-ID")

    # 11. No impact on SpendRequest budget accounting
    def test_checkout_has_no_foreign_key_to_spend_request(self):
        from django.db.models.fields.related import ForeignKey

        fk_fields = [
            f.name for f in CheckoutOrder._meta.get_fields() if isinstance(f, ForeignKey)
        ]
        self.assertNotIn("spend_request", fk_fields)

    def test_checkout_amount_not_counted_in_spend_budget(self):
        SpendRequest.objects.create(
            organization=self.organization,
            agent=self.agent,
            policy=self.policy,
            policy_version=self.policy.version,
            amount_minor=5000,
            currency="USD",
            merchant_ref="acme.com",
            decision=SpendRequest.Decision.ALLOW,
            status=SpendRequest.Status.APPROVED,
        )
        checkout = self.make_checkout(amount_minor=2000, currency="USD")
        checkout.transition_to(CheckoutOrder.Status.PAYER_ACTION_REQUIRED)
        checkout.transition_to(CheckoutOrder.Status.APPROVED)
        checkout.transition_to(CheckoutOrder.Status.CAPTURE_PENDING)
        checkout.transition_to(CheckoutOrder.Status.COMPLETED)

        from datetime import timedelta

        from django.utils import timezone

        since = timezone.now() - timedelta(days=1)
        total = counted_spend(self.agent, "USD", since)
        self.assertEqual(total, 50.00)
