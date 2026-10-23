from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.policies.models import Policy
from apps.spend import services
from apps.spend.models import SpendRequest


class ApprovalExpiryTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        Policy.objects.create(agent=self.agent)
        self.spend_request, _ = services.submit_spend_request(
            self.agent,
            amount=Decimal("75.00"),
            currency="USD",
            merchant="acme.com",
            source_type=SpendRequest.SourceType.TRUSTED,
        )

    def test_command_expires_due_approvals_once(self):
        Approval.objects.filter(pk=self.spend_request.approval.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        out = StringIO()
        call_command("expire_approvals", stdout=out)
        self.assertIn("Expired 1 approval", out.getvalue())

        self.spend_request.refresh_from_db()
        self.assertEqual(self.spend_request.status, SpendRequest.Status.EXPIRED)
        self.assertEqual(
            Approval.objects.get(pk=self.spend_request.approval.pk).outcome,
            Approval.Outcome.EXPIRED,
        )
        self.assertEqual(
            AuditEvent.objects.filter(event_type=AuditEvent.EventType.APPROVAL_EXPIRED).count(),
            1,
        )

        call_command("expire_approvals", stdout=StringIO())
        self.assertEqual(
            AuditEvent.objects.filter(event_type=AuditEvent.EventType.APPROVAL_EXPIRED).count(),
            1,
        )

    def test_future_approvals_are_left_pending(self):
        call_command("expire_approvals", stdout=StringIO())
        self.assertEqual(
            Approval.objects.get(pk=self.spend_request.approval.pk).outcome,
            Approval.Outcome.PENDING,
        )
