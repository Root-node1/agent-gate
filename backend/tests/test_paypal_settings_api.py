"""Integration tests for PayPal Settings API endpoints and authorization.

Endpoints:
- GET /api/settings/paypal/status/
- POST /api/settings/paypal/probe/

Covers:
- Anonymous access (401).
- Non-admin user access (status allowed for org member; probe rejected 403).
- Admin without MFA (rejected with 403 mfa_enrollment_required).
- Admin with MFA (allowed).
- Cross-organization access attempts (admin in Org A cannot probe Org B).
- Successful probe (200 OK + AuditEvent recorded).
- Invalid credentials (400 Bad Request + error code).
- Rate limits (429 Too Many Requests).
- Circuit breaker (503 Service Unavailable + circuit_open).
- Redis unavailable (503 Service Unavailable + coordination_unavailable).
- Timeout (504 Gateway Timeout + timeout).
- Sanitized responses (zero secrets, zero tokens).
"""

import time
from unittest.mock import patch

from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.accounts.models import Organization, OrgMembership
from apps.audit.models import AuditEvent
from apps.payments.paypal.probe_coordination import (
    CoordinationError,
    CoordinationStatus,
)
from apps.payments.paypal.probe_service import ProbeResult
from apps.payments.paypal.probe_types import ProbeConnectionState, ProbeFailureReason

User = get_user_model()

STATUS_URL = "/api/settings/paypal/status/"
PROBE_URL = "/api/settings/paypal/probe/"


@override_settings(
    PAYPAL_ENV="sandbox",
    PAYPAL_CLIENT_ID="AX1234567899Z",
    PAYPAL_CLIENT_SECRET="secret-sandbox-val",
    PAYPAL_WEBHOOK_ID="WH-9876543210",
    PAYPAL_CHECKOUT_ENABLED="true",
    PAYPAL_PAYOUTS_ENABLED="false",
)
class PayPalSettingsApiTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

        self.org_a = Organization.objects.create(name="Org Alpha")
        self.org_b = Organization.objects.create(name="Org Beta")

        # Admin user in Org A with MFA
        self.admin_user = User.objects.create_user(
            username="admin_a", email="admin_a@example.com", password="password123"
        )
        OrgMembership.objects.create(
            user=self.admin_user, organization=self.org_a, role=OrgMembership.Role.ADMIN
        )
        # Enroll MFA for admin_user
        Authenticator.objects.create(
            user=self.admin_user,
            type=Authenticator.Type.TOTP,
            data={"secret": "base32secret"},
        )

        # Admin user in Org B with MFA
        self.admin_user_b = User.objects.create_user(
            username="admin_b", email="admin_b@example.com", password="password123"
        )
        OrgMembership.objects.create(
            user=self.admin_user_b, organization=self.org_b, role=OrgMembership.Role.ADMIN
        )
        Authenticator.objects.create(
            user=self.admin_user_b,
            type=Authenticator.Type.TOTP,
            data={"secret": "base32secretB"},
        )

        # Admin user without MFA
        self.admin_no_mfa = User.objects.create_user(
            username="admin_no_mfa", email="no_mfa@example.com", password="password123"
        )
        OrgMembership.objects.create(
            user=self.admin_no_mfa, organization=self.org_a, role=OrgMembership.Role.ADMIN
        )

        # Regular member (viewer) in Org A
        self.viewer_user = User.objects.create_user(
            username="viewer_a", email="viewer_a@example.com", password="password123"
        )
        OrgMembership.objects.create(
            user=self.viewer_user, organization=self.org_a, role=OrgMembership.Role.VIEWER
        )

        self.client = Client()

    def test_anonymous_access_rejected_on_status_and_probe(self):
        res_status = self.client.get(STATUS_URL)
        self.assertEqual(res_status.status_code, 401)

        res_probe = self.client.post(PROBE_URL, data={}, content_type="application/json")
        self.assertEqual(res_probe.status_code, 401)

    def test_viewer_can_read_status_but_cannot_probe(self):
        self.client.force_login(self.viewer_user)

        res_status = self.client.get(STATUS_URL)
        self.assertEqual(res_status.status_code, 200)
        data = res_status.json()
        self.assertEqual(data["state"], ProbeConnectionState.CONFIGURED)
        self.assertFalse(data["live_payments_enabled"])
        self.assertEqual(data["client_id_preview"], "AX1...99Z")
        self.assertNotIn("secret-sandbox-val", res_status.content.decode())
        self.assertNotIn("AX1234567899Z", res_status.content.decode())

        # Viewer attempting probe must be 403 Forbidden
        res_probe = self.client.post(PROBE_URL, data={}, content_type="application/json")
        self.assertEqual(res_probe.status_code, 403)

    def test_admin_without_mfa_is_rejected_on_probe(self):
        self.client.force_login(self.admin_no_mfa)
        res_probe = self.client.post(PROBE_URL, data={}, content_type="application/json")
        self.assertEqual(res_probe.status_code, 403)
        self.assertIn("mfa_enrollment_required", str(res_probe.content))

    @patch("apps.payments.settings_views.execute_sandbox_oauth_probe")
    def test_admin_with_mfa_successful_probe(self, mock_probe):
        now_ts = time.time()
        mock_probe.return_value = ProbeResult(
            success=True,
            latency_ms=145,
            error_code=None,
            tested_at=now_ts,
        )

        self.client.force_login(self.admin_user)
        res = self.client.post(PROBE_URL, data={}, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["state"], "successfully_tested")
        self.assertEqual(data["latency_ms"], 145)
        self.assertIsNone(data["error"])
        self.assertNotIn("secret-sandbox-val", res.content.decode())
        self.assertNotIn("AX1234567899Z", res.content.decode())

        # Verify AuditEvent is recorded in database
        audit_event = AuditEvent.objects.filter(
            event_type=AuditEvent.EventType.INTEGRATION_PROBED,
            organization=self.org_a,
        ).first()
        self.assertIsNotNone(audit_event)
        self.assertEqual(audit_event.actor_id, str(self.admin_user.id))
        self.assertTrue(audit_event.payload.get("success"))
        self.assertEqual(audit_event.payload.get("latency_ms"), 145)

        # Confirm status endpoint reflects the success
        res_status = self.client.get(STATUS_URL)
        self.assertEqual(res_status.json()["state"], ProbeConnectionState.SUCCESSFULLY_TESTED)

    @patch("apps.payments.settings_views.execute_sandbox_oauth_probe")
    def test_invalid_credentials_returns_400_and_records_audit(self, mock_probe):
        mock_probe.return_value = ProbeResult(
            success=False,
            latency_ms=210,
            error_code=ProbeFailureReason.INVALID_CREDENTIALS,
            tested_at=1700000000.0,
        )

        self.client.force_login(self.admin_user)
        res = self.client.post(PROBE_URL, data={}, content_type="application/json")
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertEqual(data["state"], "failed")
        self.assertEqual(data["error"], ProbeFailureReason.INVALID_CREDENTIALS)

        # AuditEvent records sanitized failure
        audit_event = AuditEvent.objects.filter(
            event_type=AuditEvent.EventType.INTEGRATION_PROBED,
            organization=self.org_a,
        ).first()
        self.assertIsNotNone(audit_event)
        self.assertFalse(audit_event.payload.get("success"))
        self.assertEqual(audit_event.payload.get("error_code"), ProbeFailureReason.INVALID_CREDENTIALS)

    @patch("apps.payments.settings_views.check_and_increment_probe_limits")
    def test_rate_limit_rejection_returns_429_and_does_not_probe_upstream(self, mock_limits):
        mock_limits.return_value = CoordinationStatus(
            allowed=False,
            rejection_reason=ProbeFailureReason.RATE_LIMITED,
            retry_after=300,
        )

        self.client.force_login(self.admin_user)
        res = self.client.post(PROBE_URL, data={}, content_type="application/json")
        self.assertEqual(res.status_code, 429)
        data = res.json()
        self.assertEqual(data["error"], "rate_limited")
        self.assertEqual(data["retry_after"], 300)

        # Must NOT record integration.probed audit event for local rejection
        self.assertEqual(
            AuditEvent.objects.filter(event_type=AuditEvent.EventType.INTEGRATION_PROBED).count(), 0
        )

    @patch("apps.payments.settings_views.check_and_increment_probe_limits")
    def test_circuit_breaker_rejection_returns_503(self, mock_limits):
        mock_limits.return_value = CoordinationStatus(
            allowed=False,
            rejection_reason=ProbeFailureReason.CIRCUIT_OPEN,
            retry_after=60,
        )

        self.client.force_login(self.admin_user)
        res = self.client.post(PROBE_URL, data={}, content_type="application/json")
        self.assertEqual(res.status_code, 503)
        data = res.json()
        self.assertEqual(data["error"], "circuit_open")
        self.assertEqual(data["retry_after"], 60)

    @patch("apps.payments.settings_views.check_and_increment_probe_limits")
    def test_coordination_unavailable_fails_closed_with_503(self, mock_limits):
        mock_limits.side_effect = CoordinationError("Redis is down")

        self.client.force_login(self.admin_user)
        res = self.client.post(PROBE_URL, data={}, content_type="application/json")
        self.assertEqual(res.status_code, 503)
        data = res.json()
        self.assertEqual(data["error"], "coordination_unavailable")

    @patch("apps.payments.settings_views.execute_sandbox_oauth_probe")
    def test_timeout_returns_504(self, mock_probe):
        mock_probe.return_value = ProbeResult(
            success=False,
            latency_ms=8000,
            error_code=ProbeFailureReason.TIMEOUT,
            tested_at=1700000000.0,
        )

        self.client.force_login(self.admin_user)
        res = self.client.post(PROBE_URL, data={}, content_type="application/json")
        self.assertEqual(res.status_code, 504)
        data = res.json()
        self.assertEqual(data["state"], "failed")
        self.assertEqual(data["error"], "timeout")

    def test_browser_supplied_org_id_is_ignored(self):
        """Verify that supplying an arbitrary organization ID in the request does not bypass authorization."""
        self.client.force_login(self.admin_user_b)  # Admin of Org B

        # Attempt to probe while injecting Org A's ID
        with patch("apps.payments.settings_views.execute_sandbox_oauth_probe") as mock_probe:
            mock_probe.return_value = ProbeResult(
                success=True, latency_ms=100, error_code=None, tested_at=1700000000.0
            )
            res = self.client.post(
                PROBE_URL,
                data={"organization_id": str(self.org_a.id)},
                content_type="application/json",
            )
            self.assertEqual(res.status_code, 200)

            # Audit event must be attributed to Org B (user's actual org), NOT Org A
            event_b = AuditEvent.objects.filter(
                organization=self.org_b,
                event_type=AuditEvent.EventType.INTEGRATION_PROBED,
            ).first()
            self.assertIsNotNone(event_b)
            self.assertEqual(
                AuditEvent.objects.filter(
                    organization=self.org_a,
                    event_type=AuditEvent.EventType.INTEGRATION_PROBED,
                ).count(),
                0,
            )
