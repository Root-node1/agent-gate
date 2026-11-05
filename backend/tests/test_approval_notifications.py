from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.approvals.models import Approval
from apps.approvals.notifications import approval_created
from apps.policies.models import Policy
from apps.spend.models import SpendRequest


class ApprovalNotificationTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)
        self.spend_request = SpendRequest.objects.create(
            organization=self.organization,
            agent=self.agent,
            policy=self.policy,
            policy_version=self.policy.version,
            amount_minor=100,
            currency="USD",
            merchant_ref="acme.com",
            decision=SpendRequest.Decision.NEEDS_APPROVAL,
            status=SpendRequest.Status.PENDING_APPROVAL,
        )
        self.received = []

        def receiver(sender, approval, **kwargs):
            self.received.append(approval.pk)

        self.receiver = receiver
        approval_created.connect(receiver, weak=False)

    def tearDown(self):
        approval_created.disconnect(self.receiver)

    def test_new_approval_emits_the_signal(self):
        approval = Approval.objects.create(
            organization=self.organization,
            spend_request=self.spend_request,
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        self.assertEqual(self.received, [approval.pk])

    def test_updating_an_approval_does_not_emit_again(self):
        approval = Approval.objects.create(
            organization=self.organization,
            spend_request=self.spend_request,
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        approval.note = "reviewed"
        approval.save(update_fields=["note", "updated_at"])
        self.assertEqual(self.received, [approval.pk])
