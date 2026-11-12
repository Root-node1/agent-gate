"""
Payment Security and AI Advisory Boundary — Audit Tests

**Validates: Requirements 1.25, 1.26, 1.27, 1.28**

This is a BUG CONDITION EXPLORATION TEST that inspects the backend policy
pipeline and audit models to confirm that the security controls are correctly
in place:

  1.25 — AI classification is advisory only (ClassifierResult, not a decision)
  1.26 — AI advisory cannot override a DENY decision
  1.27 — AuditEvent is append-only (no frontend fabrication path)
  1.28 — There is no frontend-accessible HTTP endpoint for audit event creation

EXPECTED OUTCOME: All tests PASS — confirming the security controls are
already correct. If any test FAILS, the boundary has a gap that needs fixing.
"""

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APITestCase

import engine
from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.policies.models import Policy
from apps.spend import classifier, pipeline
from apps.spend.models import SpendRequest

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: classifier.classify() returns ClassifierResult (advisory type)
# Requirement 1.25
# ─────────────────────────────────────────────────────────────────────────────

class ClassifierReturnsAdvisoryTypeTests(TestCase):
    """classifier.classify() must return engine.ClassifierResult — an advisory
    type, not a policy decision (ALLOW / DENY / NEEDS_APPROVAL)."""

    def test_classify_returns_classifier_result_instance(self):
        """The result type is ClassifierResult, the advisory container."""
        result = classifier.classify("pay this invoice for acme.com")
        self.assertIsInstance(
            result,
            engine.ClassifierResult,
            "classifier.classify() must return engine.ClassifierResult (advisory) — "
            "not an ALLOW/DENY/NEEDS_APPROVAL decision. "
            "If this fails, the classifier is returning a decision type directly.",
        )

    def test_classify_result_is_not_a_decision(self):
        """ClassifierResult is not engine.Decision."""
        result = classifier.classify("pay this invoice for acme.com")
        self.assertNotIsInstance(
            result,
            engine.Decision,
            "classifier.classify() must return ClassifierResult (advisory), "
            "not an engine.Decision (authoritative). "
            "Returning a Decision would make AI advisory authoritative — Req 1.25.",
        )

    def test_classify_unavailable_result_is_still_classifier_result(self):
        """An unavailable (no provider) result is still ClassifierResult."""
        # With no INJECTION_CLASSIFIER configured the default fallback applies.
        result = classifier.classify("pay this invoice")
        self.assertIsInstance(result, engine.ClassifierResult)
        # available == False when no provider is configured — advisory null signal
        # is still advisory, not a denial.
        self.assertFalse(
            result.available,
            "An unconfigured classifier should produce an unavailable ClassifierResult, "
            "not raise or return a decision.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: _decide() uses engine.evaluate_context() as authoritative engine
# Requirement 1.25
# ─────────────────────────────────────────────────────────────────────────────

class DecideUsesEvaluateContextTests(TestCase):
    """The pipeline's _decide() must call engine.evaluate_context() as the
    authoritative decision — not use the ScreeningResult / ClassifierResult
    directly as the final outcome."""

    def setUp(self):
        self.organization = Organization.objects.create(name="boundary-test-org")
        self.agent, _ = Agent.create_with_key("boundary-agent", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)

    def test_decide_calls_evaluate_context(self):
        """engine.evaluate_context is called during _decide — it is the authority."""
        with patch("apps.spend.pipeline.engine.evaluate_context") as mock_eval:
            mock_eval.return_value = engine.Decision(
                outcome=engine.ALLOW,
                reasons=(),
                risk_score=0,
            )
            pipeline.submit_spend_request(
                self.agent,
                amount=Decimal("5.00"),
                currency="USD",
                merchant="acme.com",
                source_type=SpendRequest.SourceType.TRUSTED,
                idempotency_key=str(uuid4()),
            )
        mock_eval.assert_called_once()

    def test_decide_passes_screening_result_as_advisory_input(self):
        """The ScreeningResult (which carries ClassifierResult) is passed as
        advisory *input* to evaluate_context, not used as the decision itself."""
        captured = {}

        def capture_context(context):
            captured["context"] = context
            return engine.evaluate_context.__wrapped__(context) if hasattr(
                engine.evaluate_context, "__wrapped__"
            ) else engine.evaluate_context(context)

        # We just verify the context carries a ScreeningResult, not that the
        # ScreeningResult alone determined the outcome.
        with patch("apps.spend.pipeline.engine.evaluate_context", side_effect=capture_context) as mock_eval:
            # Provide a low-risk classifier signal
            mock_eval.side_effect = None
            mock_eval.return_value = engine.Decision(
                outcome=engine.ALLOW,
                reasons=(),
                risk_score=5,
            )
            pipeline.submit_spend_request(
                self.agent,
                amount=Decimal("5.00"),
                currency="USD",
                merchant="acme.com",
                source_type=SpendRequest.SourceType.TRUSTED,
                idempotency_key=str(uuid4()),
            )

        # evaluate_context was called (the deterministic engine ran)
        mock_eval.assert_called_once()
        ctx = mock_eval.call_args[0][0]
        # The EvaluationContext carries a screening field — advisory input
        self.assertIsInstance(ctx, engine.EvaluationContext)
        self.assertIsInstance(
            ctx.screening,
            engine.ScreeningResult,
            "EvaluationContext.screening must carry a ScreeningResult (advisory input). "
            "The classifier output must be passed as advisory, never as the decision itself.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: AI "low risk" advisory cannot override a DENY decision
# Requirement 1.26
# ─────────────────────────────────────────────────────────────────────────────

def _mock_low_risk_classifier(*texts):
    """Module-level mock: simulates an AI classifier returning a very low risk score.

    This is at module level so Django's import_string can resolve it via
    'tests.test_ai_advisory_boundary_audit._mock_low_risk_classifier'.
    """
    return engine.ClassifierResult(score=0, reasons=("no_risk_detected",))


class AiAdvisoryCannotOverrideDenyTests(TestCase):
    """An AI advisory classification of 'low risk' (score=0, no reasons) must
    not override a DENY produced by the deterministic policy engine."""

    def setUp(self):
        self.organization = Organization.objects.create(name="deny-override-org")
        self.agent, _ = Agent.create_with_key("deny-override-agent", self.organization)
        # Policy with a very tight per-transaction cap (100 cents = $1.00).
        # approval_threshold must be <= per_transaction_cap (DB constraint).
        self.policy = Policy.objects.create(
            agent=self.agent,
            per_transaction_cap_minor=100,     # $1.00 cap — $50 will DENY
            approval_threshold_minor=50,       # must be <= per_transaction_cap_minor
            daily_budget_minor=1_000_000,
            weekly_budget_minor=5_000_000,
            monthly_budget_minor=20_000_000,
        )

    def test_deny_stands_when_classifier_says_low_risk(self):
        """Submit a request that exceeds the per-transaction cap.
        Even if the AI classifier signals 'low risk', the DENY must stand."""
        low_risk_path = "tests.test_ai_advisory_boundary_audit._mock_low_risk_classifier"

        with self.settings(INJECTION_CLASSIFIER=low_risk_path):
            spend_request, replayed = pipeline.submit_spend_request(
                self.agent,
                amount=Decimal("50.00"),   # Way over the $1 cap
                currency="USD",
                merchant="acme.com",
                source_type=SpendRequest.SourceType.TRUSTED,
                idempotency_key=str(uuid4()),
            )

        self.assertFalse(replayed)
        self.assertEqual(
            spend_request.status,
            SpendRequest.Status.DENIED,
            "BUG (Req 1.26): A DENY decision was overridden by an AI advisory 'low risk' "
            "classification. The deterministic policy engine must remain authoritative — "
            "AI advisory must never override DENY.",
        )
        self.assertEqual(
            spend_request.decision,
            SpendRequest.Decision.DENY,
            "BUG (Req 1.26): spend_request.decision must be DENY when the policy "
            "engine denies — AI advisory must not change this.",
        )

    def test_outcome_status_mapping_uses_engine_constants(self):
        """OUTCOME_STATUS maps engine constants to status — not classifier output."""
        self.assertIn(engine.ALLOW, pipeline.OUTCOME_STATUS)
        self.assertIn(engine.DENY, pipeline.OUTCOME_STATUS)
        self.assertIn(engine.NEEDS_APPROVAL, pipeline.OUTCOME_STATUS)
        self.assertEqual(pipeline.OUTCOME_STATUS[engine.DENY], SpendRequest.Status.DENIED)
        self.assertEqual(pipeline.OUTCOME_STATUS[engine.ALLOW], SpendRequest.Status.APPROVED)
        self.assertEqual(
            pipeline.OUTCOME_STATUS[engine.NEEDS_APPROVAL],
            SpendRequest.Status.PENDING_APPROVAL,
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: AuditEvent.save() raises PermissionError on modification
# Requirement 1.27
# ─────────────────────────────────────────────────────────────────────────────

class AuditEventAppendOnlyTests(TestCase):
    """AuditEvent is append-only. Attempts to modify or delete an existing
    event must raise PermissionError — preventing any fabrication."""

    def setUp(self):
        self.organization = Organization.objects.create(name="audit-immutable-org")
        self.event = AuditEvent.record(
            AuditEvent.EventType.DECISION_MADE,
            organization=self.organization,
            decision="ALLOW",
        )

    def test_save_on_existing_event_raises_permission_error(self):
        """Calling save() on an already-persisted event must raise PermissionError."""
        # Reload from DB to ensure _state.adding is False
        event = AuditEvent.objects.get(pk=self.event.pk)
        self.assertFalse(
            event._state.adding,
            "Event loaded from DB should have _state.adding == False",
        )
        with self.assertRaises(
            PermissionError,
            msg="BUG (Req 1.27): AuditEvent.save() on an existing event did not raise "
                "PermissionError — audit events must be append-only and immutable after creation.",
        ):
            event.save()

    def test_save_error_message_is_correct(self):
        """The PermissionError message must clearly state events are append-only."""
        event = AuditEvent.objects.get(pk=self.event.pk)
        try:
            event.save()
            self.fail("Expected PermissionError was not raised")
        except PermissionError as exc:
            self.assertIn(
                "append-only",
                str(exc).lower(),
                "PermissionError message must mention 'append-only'.",
            )
            self.assertIn(
                "modified",
                str(exc).lower(),
                "PermissionError message must mention 'modified'.",
            )

    def test_modifying_payload_and_saving_raises_permission_error(self):
        """Even a seemingly innocuous payload change must be blocked."""
        event = AuditEvent.objects.get(pk=self.event.pk)
        event.payload = {"fabricated": True}
        with self.assertRaises(PermissionError):
            event.save()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: AuditEvent.delete() raises PermissionError
# Requirement 1.27
# ─────────────────────────────────────────────────────────────────────────────

class AuditEventCannotBeDeletedTests(TestCase):
    """AuditEvent.delete() must raise PermissionError — audit records are
    permanent and cannot be erased from the trail."""

    def setUp(self):
        self.organization = Organization.objects.create(name="audit-delete-org")
        self.event = AuditEvent.record(
            AuditEvent.EventType.REQUEST_RECEIVED,
            organization=self.organization,
        )

    def test_delete_raises_permission_error(self):
        """Direct .delete() on an AuditEvent instance must raise PermissionError."""
        event = AuditEvent.objects.get(pk=self.event.pk)
        with self.assertRaises(
            PermissionError,
            msg="BUG (Req 1.27): AuditEvent.delete() did not raise PermissionError — "
                "audit events must be append-only and cannot be deleted.",
        ):
            event.delete()

    def test_delete_error_message_is_correct(self):
        """The PermissionError message must clearly state events cannot be deleted."""
        event = AuditEvent.objects.get(pk=self.event.pk)
        try:
            event.delete()
            self.fail("Expected PermissionError was not raised")
        except PermissionError as exc:
            self.assertIn(
                "deleted",
                str(exc).lower(),
                "PermissionError message must mention 'deleted'.",
            )

    def test_event_still_exists_after_failed_delete(self):
        """After a failed delete attempt, the record must still be in the database."""
        event = AuditEvent.objects.get(pk=self.event.pk)
        try:
            event.delete()
        except PermissionError:
            pass
        self.assertTrue(
            AuditEvent.objects.filter(pk=self.event.pk).exists(),
            "BUG: AuditEvent was deleted despite PermissionError — the record must "
            "remain in the database after a blocked delete attempt.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: No frontend-accessible HTTP endpoint for audit event creation
# Requirement 1.27
# ─────────────────────────────────────────────────────────────────────────────

class NoFrontendAuditCreationEndpointTests(APITestCase):
    """There must be no HTTP endpoint under /v1/audit/ or /api/audit/ that
    accepts a POST payload to create audit events. All audit events must
    originate server-side from actual backend operations."""

    def setUp(self):
        self.organization = Organization.objects.create(name="no-create-endpoint-org")
        self.user = User.objects.create_user("audit-viewer")
        OrgMembership.objects.create(
            user=self.user,
            organization=self.organization,
            role=OrgMembership.Role.VIEWER,
        )
        self.client.force_authenticate(user=self.user)

    def test_post_to_v1_audit_is_method_not_allowed(self):
        """POST /v1/audit/ must not be a valid endpoint (405 or 404)."""
        response = self.client.post(
            "/v1/audit/",
            data={
                "event_type": "decision.made",
                "actor_type": "system",
                "payload": {"fabricated": True},
            },
            format="json",
        )
        self.assertIn(
            response.status_code,
            [404, 405],
            f"BUG (Req 1.27): POST /v1/audit/ returned {response.status_code} — "
            "expected 404 or 405. There must be no endpoint that allows frontend "
            "interactions to create audit events. Audit events must originate "
            "server-side only.",
        )

    def test_post_to_v1_audit_does_not_create_a_record(self):
        """Even if POST /v1/audit/ returns any response, no AuditEvent row
        should have been created from the POST payload."""
        count_before = AuditEvent.objects.filter(
            organization=self.organization
        ).count()

        self.client.post(
            "/v1/audit/",
            data={
                "event_type": "decision.made",
                "actor_type": "system",
                "organization": str(self.organization.pk),
                "payload": {"fabricated": True},
            },
            format="json",
        )

        count_after = AuditEvent.objects.filter(
            organization=self.organization
        ).count()
        self.assertEqual(
            count_before,
            count_after,
            "BUG (Req 1.27): A POST to /v1/audit/ created an AuditEvent record — "
            "frontend interactions must never be able to create or falsify audit events. "
            "All audit events must originate server-side from actual backend operations.",
        )

    def test_no_audit_create_route_in_v1_namespace(self):
        """Confirm there is no /v1/audit/create/ or /v1/audit/events/ POST route."""
        for path in ["/v1/audit/create/", "/v1/audit/events/", "/v1/audit/new/"]:
            response = self.client.post(
                path,
                data={"event_type": "decision.made"},
                format="json",
            )
            self.assertIn(
                response.status_code,
                [404, 405],
                f"BUG (Req 1.27): POST {path} returned {response.status_code} — "
                "this path should not exist as an audit event creation endpoint.",
            )

    def test_no_audit_create_route_in_api_namespace(self):
        """Confirm there is no /api/audit/ POST route either."""
        response = self.client.post(
            "/api/audit/",
            data={"event_type": "decision.made"},
            format="json",
        )
        self.assertIn(
            response.status_code,
            [404, 405],
            f"BUG (Req 1.27): POST /api/audit/ returned {response.status_code} — "
            "this path should not exist as an audit event creation endpoint.",
        )

    def test_audit_list_endpoint_is_get_only(self):
        """The /v1/audit/ list endpoint must be GET-only (read access, not write)."""
        # GET should succeed (200) for authenticated users
        response_get = self.client.get("/v1/audit/")
        self.assertEqual(
            response_get.status_code,
            200,
            "GET /v1/audit/ must return 200 for authenticated users.",
        )
        # POST must be rejected
        response_post = self.client.post("/v1/audit/", data={}, format="json")
        self.assertIn(
            response_post.status_code,
            [404, 405],
            f"BUG (Req 1.27): POST /v1/audit/ returned {response_post.status_code}. "
            "The audit list endpoint must be read-only (GET only).",
        )

    def test_unauthenticated_post_to_audit_is_rejected(self):
        """An unauthenticated POST to /v1/audit/ must be rejected (401 or 404/405)."""
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/v1/audit/",
            data={"event_type": "decision.made"},
            format="json",
        )
        self.assertIn(
            response.status_code,
            [401, 403, 404, 405],
            f"BUG (Req 1.27): Unauthenticated POST /v1/audit/ returned "
            f"{response.status_code} — must be rejected.",
        )
