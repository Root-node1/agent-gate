from io import StringIO
from unittest import skipUnless

from django.core.management import call_command
from django.db import connection
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.audit.models import AuditEvent


class AuditApiTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.other = Organization.objects.create(name="other")
        self.viewer = self.member("viewer", OrgMembership.Role.VIEWER)
        self.admin = self.member("admin", OrgMembership.Role.ADMIN)
        self.event = AuditEvent.record(
            AuditEvent.EventType.DECISION_MADE, organization=self.organization, amount="10.00"
        )
        AuditEvent.record(AuditEvent.EventType.REQUEST_RECEIVED, organization=self.other)

    def member(self, name, role):
        user = User.objects.create_user(name)
        OrgMembership.objects.create(user=user, organization=self.organization, role=role)
        return user

    def test_list_is_scoped_and_filterable(self):
        self.client.force_authenticate(user=self.viewer)
        body = self.client.get("/v1/audit/").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], self.event.pk)

        filtered = self.client.get("/v1/audit/?event_type=request.received").json()
        self.assertEqual(filtered["count"], 0)
        bad = self.client.get("/v1/audit/?event_type=made.up")
        self.assertEqual(bad.status_code, 400)

    def test_invalid_filters_are_rejected(self):
        self.client.force_authenticate(user=self.viewer)
        self.assertEqual(self.client.get("/v1/audit/?agent=nope").status_code, 400)
        self.assertEqual(self.client.get("/v1/audit/?spend_request=nope").status_code, 400)
        self.assertEqual(self.client.get("/v1/audit/?after=nope").status_code, 400)

    def test_after_returns_newer_events_in_order(self):
        newer = AuditEvent.record(
            AuditEvent.EventType.APPROVAL_REQUESTED, organization=self.organization
        )
        self.client.force_authenticate(user=self.viewer)
        body = self.client.get(f"/v1/audit/?after={self.event.pk}").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], newer.pk)

    def test_verify_requires_admin(self):
        self.client.force_authenticate(user=self.viewer)
        self.assertEqual(self.client.get("/v1/audit/verify/").status_code, 403)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/v1/audit/verify/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checked"], 1)
        self.assertEqual(response.json()["organizations"], 1)

    @skipUnless(connection.vendor == "sqlite", "the PostgreSQL trigger blocks this tampering")
    def test_verify_reports_tampering(self):
        AuditEvent.objects.filter(pk=self.event.pk).update(payload={"amount": "99.00"})
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/v1/audit/verify/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["event"], self.event.pk)

    def test_command_uses_the_same_verifier(self):
        out = StringIO()
        call_command("verify_audit", stdout=out)
        self.assertIn("2 event(s)", out.getvalue())
