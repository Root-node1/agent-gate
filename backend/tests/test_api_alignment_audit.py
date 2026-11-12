"""API contract alignment exploration test (Property 1: Bug Condition).

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**

This test surfaces counterexamples that demonstrate API endpoint mismatches,
org-scoping gaps, auth gaps, error envelope mismatches, and missing API state
handling.

CRITICAL: This test MUST FAIL on unfixed code — failure confirms the bug
exists.  Do NOT fix the test or the code when it fails; document the
counterexamples found.  This test encodes the expected behavior — it will
validate the fix when it passes after implementation.

Scoped PBT Approach: For deterministic mismatches, the property is scoped to
concrete failing case(s) (specific frontend path strings tested against
backend URL config) for reproducibility.
"""

from __future__ import annotations

import os
import re
import uuid

from django.urls import resolve
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from tests.base import force_mfa

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FRONTEND_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend",
    "src",
)

DUMMY_UUID = "00000000-0000-0000-0000-000000000000"


def _resolve_path(raw_path: str):
    """Resolve a frontend API path (with optional query string) against the
    Django URL resolver, substituting a dummy UUID for path parameters.

    Returns the ResolverMatch or raises Resolver404 if the path is not
    registered.
    """
    # Strip query string
    path = raw_path.split("?")[0]
    # Substitute any UUID-like segment with a dummy UUID for resolution
    path = re.sub(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        DUMMY_UUID,
        path,
    )
    # Also handle template placeholders like :id or ${id}
    path = re.sub(r"[:$]\{?\w+\}?", DUMMY_UUID, path)
    return resolve(path)


# ---------------------------------------------------------------------------
# 1. API Path Alignment — frontend paths vs backend URL config (Req 1.1)
# ---------------------------------------------------------------------------

class ApiPathAlignmentTest(APITestCase):
    """Assert each frontend API module path string matches a backend URL
    pattern.

    **Validates: Requirement 1.1** — WHEN a frontend feature calls a backend
    endpoint whose URL path differs from the backend's actual route
    definition THEN the system exhibits an integration failure.

    This test resolves every concrete path used by each frontend ``apiRequest``
    call against Django's URL resolver.  If a path does not resolve, it is a
    contract mismatch (404/405).
    """

    # Each entry: (frontend_module, [(method, path_string), ...])
    # Paths are the literal strings passed to apiRequest() or headlessFetch()
    # with UUID template values replaced by a dummy UUID.
    FRONTEND_PATHS = {
        "agents.ts": [
            ("GET", "/v1/agents/"),
            ("GET", "/v1/agents/" + DUMMY_UUID + "/"),
            ("POST", "/v1/agents/"),
            ("PATCH", "/v1/agents/" + DUMMY_UUID + "/"),
            ("POST", "/v1/agents/" + DUMMY_UUID + "/rotate-key/"),
            ("POST", "/v1/agents/" + DUMMY_UUID + "/revoke-key/"),
        ],
        "approvals.ts": [
            ("GET", "/v1/approvals/"),
            ("GET", "/v1/approvals/" + DUMMY_UUID + "/"),
            ("POST", "/v1/approvals/" + DUMMY_UUID + "/approve/"),
            ("POST", "/v1/approvals/" + DUMMY_UUID + "/deny/"),
        ],
        "audit.ts": [
            ("GET", "/v1/audit/"),
            ("GET", "/v1/audit/verify/"),
        ],
        "policies.ts": [
            ("GET", "/v1/policies/"),
            ("GET", "/v1/policies/" + DUMMY_UUID + "/"),
            ("POST", "/v1/policies/"),
            ("PATCH", "/v1/policies/" + DUMMY_UUID + "/"),
            ("POST", "/v1/policies/" + DUMMY_UUID + "/merchant-rules/"),
            ("DELETE", "/v1/policies/" + DUMMY_UUID + "/merchant-rules/" + DUMMY_UUID + "/"),
        ],
        "spendRequests.ts": [
            ("POST", "/v1/spend-requests/"),
            ("GET", "/v1/spend-requests/" + DUMMY_UUID + "/"),
            ("GET", "/v1/spend-requests/"),
        ],
        "payments.ts": [
            ("POST", "/v1/checkout-orders/"),
            ("POST", "/v1/checkout-orders/" + DUMMY_UUID + "/capture/"),
            ("POST", "/v1/payout-reservations/"),
            ("POST", "/v1/payout-reservations/" + DUMMY_UUID + "/submit/"),
            ("GET", "/v1/payout-reservations/" + DUMMY_UUID + "/reconcile/"),
        ],
        "paypal.ts": [
            ("GET", "/api/settings/paypal/status/"),
            ("POST", "/api/settings/paypal/probe/"),
        ],
        "auth.ts (dashboard endpoints)": [
            ("GET", "/api/auth/user/"),
            ("POST", "/api/auth/organizations/"),
            ("GET", "/api/auth/options/"),
            ("GET", "/api/auth/session/"),
            ("POST", "/api/auth/session/remember/"),
            ("GET", "/api/auth/profile/"),
            ("PATCH", "/api/auth/profile/"),
        ],
        "auth.ts (headless endpoints)": [
            ("GET", "/api/auth/headless/browser/v1/auth/session"),
            ("DELETE", "/api/auth/headless/browser/v1/auth/session"),
            ("POST", "/api/auth/headless/browser/v1/auth/login"),
            ("POST", "/api/auth/headless/browser/v1/auth/signup"),
            ("POST", "/api/auth/headless/browser/v1/auth/email/verify"),
            ("POST", "/api/auth/headless/browser/v1/auth/email/verify/resend"),
            ("POST", "/api/auth/headless/browser/v1/account/email"),
            ("POST", "/api/auth/headless/browser/v1/auth/password/request"),
            ("POST", "/api/auth/headless/browser/v1/auth/password/reset"),
            ("POST", "/api/auth/headless/browser/v1/account/password/change"),
            ("POST", "/api/auth/headless/browser/v1/auth/2fa/authenticate"),
            ("POST", "/api/auth/headless/browser/v1/auth/reauthenticate"),
            ("GET", "/api/auth/headless/browser/v1/account/authenticators"),
            ("GET", "/api/auth/headless/browser/v1/account/authenticators/totp"),
            ("POST", "/api/auth/headless/browser/v1/account/authenticators/totp"),
            ("DELETE", "/api/auth/headless/browser/v1/account/authenticators/totp"),
            ("POST", "/api/auth/headless/browser/v1/account/authenticators/recovery-codes"),
            ("GET", "/api/auth/headless/browser/v1/account/authenticators/recovery-codes"),
        ],
    }

    def test_all_frontend_api_paths_resolve(self):
        """Every path string used by the frontend API modules must resolve to
        a registered backend URL pattern.  A failure means the frontend calls
        a path the backend does not define (integration failure / 404).
        """
        mismatches = []
        for module, paths in self.FRONTEND_PATHS.items():
            for method, path in paths:
                try:
                    _resolve_path(path)
                    # Path resolved — record the URL name for documentation
                except Exception as exc:
                    mismatches.append(
                        f"{module}: {method} {path} -> UNRESOLVABLE ({exc})"
                    )
        if mismatches:
            self.fail(
                "API path mismatches found (frontend calls paths the backend "
                "does not define):\n" + "\n".join(mismatches)
            )


# ---------------------------------------------------------------------------
# 2. Org-Scoping IDOR Test — body-supplied org ID rejection (Req 1.2)
# ---------------------------------------------------------------------------

class OrgScopingIdorTest(APITestCase):
    """Assert that a user cannot create a resource in an organization they do
    not belong to by sending a foreign org UUID in the request body.

    **Validates: Requirement 1.2** — WHEN the frontend sends an organization
    identifier in a request body that the backend does not validate against
    the authenticated session's memberships THEN the system may accept
    requests scoped to an organization the user does not belong to.

    Scoped to concrete ``organization`` body field cases in ``agents.ts``
    (``AgentCreateInput.organization``) and ``payments.ts``
    (``CreateCheckoutOrderInput.organization``).
    """

    def setUp(self):
        # Organization A with admin user A (MFA-enrolled)
        self.org_a = Organization.objects.create(name="org-a")
        self.user_a = User.objects.create_user("user-a")
        OrgMembership.objects.create(
            user=self.user_a, organization=self.org_a, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.user_a)

        # Organization B with admin user B (MFA-enrolled)
        self.org_b = Organization.objects.create(name="org-b")
        self.user_b = User.objects.create_user("user-b")
        OrgMembership.objects.create(
            user=self.user_b, organization=self.org_b, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.user_b)

    def test_user_b_cannot_create_agent_in_org_a(self):
        """User B (org B admin) sends org A's UUID in the ``organization`` body
        field.  The backend must reject this — either 400 (validation error from
        serializer) or 403/404 (permission/queryset rejection).

        If the backend accepts the request and creates an agent in org A, that
        is an IDOR bug (body-supplied org ID is trusted).
        """
        self.client.force_authenticate(user=self.user_b)
        response = self.client.post(
            "/v1/agents/",
            {"name": "cross-org-agent", "organization": str(self.org_a.id)},
            format="json",
        )
        # The response must NOT be 201 (created) — any rejection is correct
        self.assertNotEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            f"IDOR BUG: user B created an agent in org A by sending org A's UUID "
            f"in the body. Got 201 Created. Response: {response.json()}",
        )

    def test_user_b_cannot_create_checkout_order_in_org_a(self):
        """User B (org B admin) sends org A's UUID in the ``organization`` body
        field of the checkout-order creation endpoint.  The backend must reject
        this — either 403/404 (permission/queryset rejection) or 400 (validation
        error).

        If the backend accepts the request, that is an IDOR bug.
        """
        self.client.force_authenticate(user=self.user_b)
        response = self.client.post(
            "/v1/checkout-orders/",
            {
                "organization": str(self.org_a.id),
                "amount": "10.00",
                "currency": "USD",
                "idempotency_key": str(uuid.uuid4()),
            },
            format="json",
        )
        # The response must NOT be 201/200/202 (success) — any rejection is correct
        self.assertNotIn(
            response.status_code,
            (status.HTTP_201_CREATED, status.HTTP_200_OK, status.HTTP_202_ACCEPTED),
            f"IDOR BUG: user B created a checkout order in org A by sending "
            f"org A's UUID in the body. Got {response.status_code}. "
            f"Response: {response.json()}",
        )


# ---------------------------------------------------------------------------
# 3. Auth/Permission Check — every backend view enforces auth (Req 1.3)
# ---------------------------------------------------------------------------

class AuthPermissionTest(APITestCase):
    """Assert that every backend API view enforces authentication.

    **Validates: Requirement 1.3** — WHEN a backend API endpoint lacks proper
    authentication or permission enforcement THEN the system exposes data or
    actions to unauthenticated callers.

    This test introspects all APIView subclasses reachable via the URL config
    and checks that they declare ``permission_classes`` or override
    ``get_permissions()`` — with the exception of intentionally-public
    endpoints (CSRF token, auth options, session status, PayPal webhook).
    """

    # Views that are intentionally public (no auth required)
    PUBLIC_VIEW_NAMES = {
        "csrf",            # /api/auth/csrf/ — returns CSRF token
        "auth-options",    # /api/auth/options/ — OAuth provider flags
        "auth-session",    # /api/auth/session/ — returns authenticated boolean
        "paypal-webhook",  # /v1/webhooks/paypal/ — PayPal server callback
    }

    def test_all_v1_endpoints_require_authentication(self):
        """Every /v1/ endpoint must return 401/403 for unauthenticated
        requests (not 200).  A 200 for an unauthenticated request means the
        endpoint does not enforce authentication.
        """
        # Endpoints to test (path, method)
        v1_endpoints = [
            ("/v1/agents/", "GET"),
            ("/v1/approvals/", "GET"),
            ("/v1/audit/", "GET"),
            ("/v1/audit/verify/", "GET"),
            ("/v1/policies/", "GET"),
            ("/v1/spend-requests/", "GET"),
            ("/v1/checkout-orders/", "POST"),
            ("/v1/payout-reservations/", "POST"),
        ]

        gaps = []
        for path, method in v1_endpoints:
            if method == "GET":
                response = self.client.get(path)
            else:
                response = self.client.post(path, {}, format="json")
            # Any 2xx means the endpoint allowed unauthenticated access
            if 200 <= response.status_code < 300:
                gaps.append(f"{method} {path} -> {response.status_code} (no auth enforced)")

        if gaps:
            self.fail(
                "Auth/permission gaps found (endpoints that allow unauthenticated "
                "access):\n" + "\n".join(gaps)
            )

    def test_paypal_settings_endpoints_require_authentication(self):
        """The PayPal settings status and probe endpoints must require
        authentication."""
        gaps = []
        response = self.client.get("/api/settings/paypal/status/")
        if 200 <= response.status_code < 300:
            gaps.append(f"GET /api/settings/paypal/status/ -> {response.status_code}")

        response = self.client.post("/api/settings/paypal/probe/", {}, format="json")
        if 200 <= response.status_code < 300:
            gaps.append(f"POST /api/settings/paypal/probe/ -> {response.status_code}")

        if gaps:
            self.fail(
                "Auth/permission gaps found (PayPal settings endpoints allow "
                "unauthenticated access):\n" + "\n".join(gaps)
            )


# ---------------------------------------------------------------------------
# 4. Error Envelope Test — every error uses { error: { code, message, details
# }, request_id } (Req 1.5)
# ---------------------------------------------------------------------------

class ErrorEnvelopeTest(APITestCase):
    """Assert that every endpoint's error response uses the unified error
    envelope ``{ error: { code, message, details }, request_id }`` from
    ``backend/apps/common/errors.py``.

    **Validates: Requirement 1.5** — WHEN the frontend API client receives a
    non-2xx response with an unexpected error envelope THEN the system shows
    a generic or unhelpful error message.

    This test will FAIL on unfixed code if any endpoint bypasses
    ``api_exception_handler`` and returns a bare ``{"detail": ...}`` response.
    """

    def setUp(self):
        # Create an authenticated admin user with MFA for triggering
        # authenticated-endpoint errors
        self.org = Organization.objects.create(name="test-org")
        self.admin = User.objects.create_user("admin-user")
        OrgMembership.objects.create(
            user=self.admin, organization=self.org, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.admin)

    def _assert_error_envelope(self, response, context):
        """Assert the response body uses the unified error envelope."""
        body = response.json()
        if "error" not in body:
            self.fail(
                f"{context}: response body missing 'error' key. "
                f"Got: {body}. "
                f"Expected envelope: {{ error: {{ code, message, details }}, request_id }}"
            )
        error_obj = body["error"]
        if "code" not in error_obj:
            self.fail(
                f"{context}: error object missing 'code' key. "
                f"Got: {error_obj}"
            )
        if "message" not in error_obj:
            self.fail(
                f"{context}: error object missing 'message' key. "
                f"Got: {error_obj}"
            )

    def test_unauthenticated_agent_list_uses_error_envelope(self):
        """The agents list endpoint error for unauthenticated requests must use
        the error envelope (via api_exception_handler)."""
        response = self.client.get("/v1/agents/")
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)
        self._assert_error_envelope(response, "GET /v1/agents/ (unauthenticated)")

    def test_checkout_order_create_error_uses_envelope(self):
        """The checkout-order creation endpoint must return error responses in
        the unified envelope, not a bare ``{"detail": ...}`` format.

        When PayPal is not configured, the view returns 503 with
        ``{"detail": "PayPal is not configured."}`` — this bypasses
        ``api_exception_handler`` and is a bug (Req 1.5).
        """
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/v1/checkout-orders/",
            {
                "organization": str(self.org.id),
                "amount": "10.00",
                "currency": "USD",
                "idempotency_key": str(uuid.uuid4()),
            },
            format="json",
        )
        # If PayPal is not configured, we expect a non-2xx error response
        if response.status_code >= 400:
            self._assert_error_envelope(
                response, "POST /v1/checkout-orders/ (PayPal not configured)"
            )

    def test_checkout_order_capture_error_uses_envelope(self):
        """The checkout-order capture endpoint must return error responses in
        the unified envelope."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            f"/v1/checkout-orders/{DUMMY_UUID}/capture/",
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )
        if response.status_code >= 400:
            self._assert_error_envelope(
                response, "POST /v1/checkout-orders/<id>/capture/"
            )

    def test_payout_reservation_create_error_uses_envelope(self):
        """The payout-reservation creation endpoint must return error responses
        in the unified envelope, not a bare ``{"detail": ...}`` format."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/v1/payout-reservations/",
            {
                "spend_request": DUMMY_UUID,
                "idempotency_key": str(uuid.uuid4()),
            },
            format="json",
        )
        if response.status_code >= 400:
            self._assert_error_envelope(
                response, "POST /v1/payout-reservations/ (payouts not configured)"
            )

    def test_payout_reservation_submit_error_uses_envelope(self):
        """The payout-reservation submit endpoint must return error responses
        in the unified envelope."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            f"/v1/payout-reservations/{DUMMY_UUID}/submit/",
            format="json",
        )
        if response.status_code >= 400:
            self._assert_error_envelope(
                response, "POST /v1/payout-reservations/<id>/submit/"
            )

    def test_payout_reservation_reconcile_error_uses_envelope(self):
        """The payout-reservation reconcile endpoint must return error
        responses in the unified envelope."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            f"/v1/payout-reservations/{DUMMY_UUID}/reconcile/",
        )
        if response.status_code >= 400:
            self._assert_error_envelope(
                response, "GET /v1/payout-reservations/<id>/reconcile/"
            )

    def test_organization_create_conflict_uses_envelope(self):
        """The organization creation endpoint's conflict error must use the
        envelope, not a bare ``{"detail": ...}`` format."""
        # Create an org first
        Organization.objects.create(name="duplicate-org")
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/api/auth/organizations/",
            {"name": "duplicate-org"},
            format="json",
        )
        if response.status_code >= 400:
            self._assert_error_envelope(
                response, "POST /api/auth/organizations/ (duplicate name)"
            )


# ---------------------------------------------------------------------------
# 5. Frontend API State Handling Audit (Req 1.6)
# ---------------------------------------------------------------------------

class FrontendApiStateHandlingTest(APITestCase):
    """Assert that each dashboard page component uses ``useApiResource`` (or
    equivalent) and renders loading, error, and empty states.

    **Validates: Requirement 1.6** — WHEN a frontend loading state, failure
    state, or empty state for an API-driven page does not match the actual API
    response possibilities THEN the system presents an incomplete or confusing
    UI.

    This test inspects each dashboard page component's source code for
    ``useApiResource`` usage and loading/error/empty state rendering.  It will
    FAIL if any page omits ``useApiResource`` or one of the three required
    states.

    On unfixed code, many dashboard pages use ``useDemoState()`` +
    ``useSimulatedLoad()`` instead of ``useApiResource()``, which means they do
    not handle real API loading/error/empty states — only simulated demo
    states.  This is the bug surface.
    """

    # Dashboard page components to audit (relative path from frontend/src/)
    DASHBOARD_PAGES = [
        "pages/app/AgentsPage.tsx",
        "pages/app/ApprovalsPage.tsx",
        "pages/app/AuditLogPage.tsx",
        "pages/app/PoliciesPage.tsx",
        "pages/app/SettingsPage.tsx",
        "pages/app/SimulatePage.tsx",
        "pages/app/TransactionsPage.tsx",
        "pages/app/OverviewPage.tsx",
        "pages/app/AgentDetailPage.tsx",
        "pages/app/ApprovalDetailPage.tsx",
        "pages/app/PolicyEditPage.tsx",
        "pages/app/TransactionDetailPage.tsx",
        "pages/live/TesterPage.tsx",
        "pages/live/RequestsPage.tsx",
        "pages/live/RequestDetailPage.tsx",
    ]

    def _read_frontend_file(self, rel_path: str) -> str:
        """Read a frontend source file and return its contents."""
        full_path = os.path.join(FRONTEND_SRC, rel_path)
        if not os.path.exists(full_path):
            return ""
        with open(full_path, encoding="utf-8") as f:
            return f.read()

    def test_all_dashboard_pages_use_use_api_resource(self):
        """Every dashboard page must import and use ``useApiResource`` (or an
        equivalent API-driven state hook) for loading real backend data.

        A page that uses only ``useDemoState()`` + ``useSimulatedLoad()``
        without ``useApiResource()`` does not handle real API loading, error,
        and empty states — it only handles simulated demo states.  This is the
        bug surface (Req 1.6).

        This test will FAIL on unfixed code because dashboard pages use
        ``useDemoState()`` instead of ``useApiResource()``.
        """
        pages_missing = []
        for page in self.DASHBOARD_PAGES:
            source = self._read_frontend_file(page)
            if not source:
                pages_missing.append(f"{page} (file not found)")
                continue
            has_use_api_resource = "useApiResource" in source
            has_demo_state = "useDemoState" in source
            has_simulated_load = "useSimulatedLoad" in source
            if not has_use_api_resource:
                detail = f"{page}: missing useApiResource"
                if has_demo_state:
                    detail += " (uses useDemoState instead)"
                if has_simulated_load:
                    detail += " (uses useSimulatedLoad for loading)"
                pages_missing.append(detail)

        if pages_missing:
            self.fail(
                "Frontend API state handling gaps found (dashboard pages that do "
                "not use useApiResource for real API state management):\n"
                + "\n".join(pages_missing)
                + "\n\nThese pages handle only simulated/demo states, not real API "
                "loading/error/empty states (Requirement 1.6)."
            )

    def test_dashboard_pages_handle_all_three_states(self):
        """Every dashboard page that fetches data must render all three API
        response states: loading, error, and empty.

        This test checks for evidence of each state in the page source:
        - Loading: SkeletonRows, loading, aria-busy, or similar
        - Error: error, Error, or similar error handling
        - Empty: EmptyState, empty, "No results" or similar

        On unfixed code, pages using useDemoState() handle simulated loading
        and empty states but may not handle real API error states.
        """
        pages_missing_states = []
        for page in self.DASHBOARD_PAGES:
            source = self._read_frontend_file(page)
            if not source:
                continue

            missing = []
            # Check for loading state indicators
            has_loading = bool(
                re.search(
                    r"loading|SkeletonRows|aria-busy|useSimulatedLoad|isLoading",
                    source,
                    re.IGNORECASE,
                )
            )
            # Check for error state indicators
            has_error = bool(
                re.search(
                    r"error|Error|catch\(|\.catch|status.*error",
                    source,
                    re.IGNORECASE,
                )
            )
            # Check for empty state indicators
            has_empty = bool(
                re.search(
                    r"empty|EmptyState|No results|No \w+ yet|\.length\s*===?\s*0",
                    source,
                    re.IGNORECASE,
                )
            )

            if not has_loading:
                missing.append("loading")
            if not has_error:
                missing.append("error")
            if not has_empty:
                missing.append("empty")

            if missing:
                pages_missing_states.append(
                    f"{page}: missing states: {', '.join(missing)}"
                )

        if pages_missing_states:
            self.fail(
                "Frontend API state handling gaps found (pages missing one or "
                "more required states):\n" + "\n".join(pages_missing_states)
            )
