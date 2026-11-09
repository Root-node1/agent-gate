from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.audit.anchors import (
    AuditAnchor,
    AuditAnchorStore,
    JsonlAuditAnchorStore,
)
from apps.audit.models import AuditEvent
from apps.audit.services import AuditChainBroken, anchor_all, verify_organizations
from tests.base import force_mfa


class InMemoryAnchorStore(AuditAnchorStore):
    def __init__(self):
        self.anchors = []

    def append(self, anchor):
        self.anchors.append(anchor)

    def latest(self, organization_id):
        for anchor in reversed(self.anchors):
            if anchor.organization_id == str(organization_id):
                return anchor
        return None


class AuditAnchorVerificationTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.first = AuditEvent.record(
            AuditEvent.EventType.DECISION_MADE,
            organization=self.organization,
            amount="10.00",
        )
        self.head = AuditEvent.record(
            AuditEvent.EventType.REQUEST_RECEIVED,
            organization=self.organization,
            amount="20.00",
        )

    def anchor(self, **overrides):
        values = {
            "organization_id": str(self.organization.pk),
            "head_event_id": self.head.pk,
            "head_hash": self.head.hash,
            "anchored_at": timezone.now(),
        }
        values.update(overrides)
        return AuditAnchor(**values)

    def test_matching_anchor_passes(self):
        store = InMemoryAnchorStore()
        self.assertEqual(anchor_all(store), 1)
        self.assertEqual(
            verify_organizations([self.organization], anchor_store=store), 2
        )

    def test_anchor_hash_mismatch_is_broken(self):
        store = InMemoryAnchorStore()
        store.append(self.anchor(head_hash="f" * 64))

        with self.assertRaises(AuditChainBroken) as caught:
            verify_organizations([self.organization], anchor_store=store)

        self.assertEqual(caught.exception.reason, "anchored hash does not match")
        self.assertEqual(caught.exception.event_id, self.head.pk)

    def test_missing_anchored_event_is_broken(self):
        store = InMemoryAnchorStore()
        store.append(self.anchor(head_event_id=self.head.pk + 100))

        with self.assertRaises(AuditChainBroken) as caught:
            verify_organizations([self.organization], anchor_store=store)

        self.assertEqual(caught.exception.reason, "anchored event is missing")

    def test_events_without_an_anchor_are_broken(self):
        store = InMemoryAnchorStore()

        with self.assertRaises(AuditChainBroken) as caught:
            verify_organizations([self.organization], anchor_store=store)

        self.assertEqual(caught.exception.reason, "no anchor found")
        self.assertEqual(caught.exception.event_id, self.head.pk)


class JsonlAuditAnchorStoreTests(TestCase):
    def test_append_and_read_latest_per_organization(self):
        with TemporaryDirectory() as directory:
            store = JsonlAuditAnchorStore(Path(directory) / "anchors.jsonl")
            now = timezone.now()
            first = AuditAnchor("org-a", 1, "a" * 64, now)
            other = AuditAnchor("org-b", 2, "b" * 64, now)
            latest = AuditAnchor("org-a", 3, "c" * 64, now + timezone.timedelta(hours=1))
            store.append(first)
            store.append(other)
            store.append(latest)

            self.assertEqual(store.latest("org-a"), latest)
            self.assertEqual(store.latest("org-b"), other)
            self.assertIsNone(store.latest("org-c"))


class AnchorCommandTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.head = AuditEvent.record(
            AuditEvent.EventType.REQUEST_RECEIVED,
            organization=self.organization,
        )

    def test_command_records_the_head_anchor(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "anchors.jsonl"
            with override_settings(AUDIT_ANCHOR_PATH=str(path)):
                call_command("anchor_audit", stdout=StringIO())

            anchor = JsonlAuditAnchorStore(path).latest(str(self.organization.pk))
            self.assertIsNotNone(anchor)
            self.assertEqual(anchor.head_event_id, self.head.pk)
            self.assertEqual(anchor.head_hash, self.head.hash)

    def test_command_requires_a_configured_store(self):
        with override_settings(AUDIT_ANCHOR_PATH=""):
            with self.assertRaises(CommandError):
                call_command("anchor_audit", stdout=StringIO())

    def test_periodic_task_records_anchors(self):
        from apps.background.tasks import anchor_audit_periodic

        with TemporaryDirectory() as directory:
            path = Path(directory) / "anchors.jsonl"
            with override_settings(AUDIT_ANCHOR_PATH=str(path)):
                self.assertEqual(anchor_audit_periodic(timestamp=0), 1)

            anchor = JsonlAuditAnchorStore(path).latest(str(self.organization.pk))
            self.assertIsNotNone(anchor)
            self.assertEqual(anchor.head_event_id, self.head.pk)

    def test_periodic_task_skips_without_a_store(self):
        from apps.background.tasks import anchor_audit_periodic

        with override_settings(AUDIT_ANCHOR_PATH=""):
            self.assertEqual(anchor_audit_periodic(timestamp=0), 0)


class AuditAnchorApiTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.admin = User.objects.create_user("admin")
        OrgMembership.objects.create(
            user=self.admin,
            organization=self.organization,
            role=OrgMembership.Role.ADMIN,
        )
        force_mfa(self.admin)
        self.head = AuditEvent.record(
            AuditEvent.EventType.REQUEST_RECEIVED,
            organization=self.organization,
        )
        self.client.force_authenticate(user=self.admin)

    def store(self, **overrides):
        values = {
            "organization_id": str(self.organization.pk),
            "head_event_id": self.head.pk,
            "head_hash": self.head.hash,
            "anchored_at": timezone.now(),
        }
        values.update(overrides)
        store = InMemoryAnchorStore()
        store.append(AuditAnchor(**values))
        return store

    def test_verify_passes_with_a_matching_anchor(self):
        with patch("apps.audit.views.get_anchor_store", return_value=self.store()):
            response = self.client.get("/v1/audit/verify/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checked"], 1)

    def test_verify_rejects_a_mutated_head_without_the_matching_anchor(self):
        store = self.store(head_hash="f" * 64)
        with patch("apps.audit.views.get_anchor_store", return_value=store):
            response = self.client.get("/v1/audit/verify/")

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["error"]["code"], "audit_chain_broken")
        self.assertEqual(body["error"]["details"]["event"], self.head.pk)
        self.assertEqual(
            body["error"]["details"]["reason"], "anchored hash does not match"
        )

    def test_verify_rejects_a_missing_anchored_event(self):
        store = self.store(head_event_id=self.head.pk + 100)
        with patch("apps.audit.views.get_anchor_store", return_value=store):
            response = self.client.get("/v1/audit/verify/")

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["error"]["code"], "audit_chain_broken")
        self.assertEqual(
            body["error"]["details"]["reason"], "anchored event is missing"
        )
