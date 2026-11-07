import json
from contextlib import ExitStack
from unittest import mock

from django.db import IntegrityError
from django.test import Client, override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.common.errors import ErrorCode
from apps.payments.paypal import PayPalResponseError, PayPalTransientError
from apps.payments.views import MAX_WEBHOOK_BYTES
from apps.policies.models import MerchantRule, Policy
from apps.policies.services import PolicyConflictError, PolicyValidationError
from tests.base import force_mfa
from tests.test_paypal_webhooks import SIGNATURE_HEADERS, StubVerifyClient, payout_event


class ErrorEnvelopeMixin:
    def assert_error_envelope(
        self, response, *, status_code, code, message, details=None
    ):
        self.assertEqual(response.status_code, status_code, response.content)
        body = response.json()
        self.assertNotIn("detail", body)
        self.assertEqual(
            body["error"],
            {
                "code": code,
                "message": message,
                "details": details or {},
            },
        )
        self.assertEqual(body["request_id"], response["X-Request-Id"])
        self.assertTrue(body["request_id"])


class AccountsErrorEnvelopeTests(ErrorEnvelopeMixin, APITestCase):
    def test_unauthenticated_endpoints_use_the_envelope(self):
        cases = [
            ("get", "/api/auth/user/"),
            ("post", "/api/auth/logout/"),
        ]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path)
                self.assert_error_envelope(
                    response,
                    status_code=401,
                    code=ErrorCode.AUTHENTICATION_FAILED.value,
                    message="Authentication failed.",
                )


class AgentErrorEnvelopeTests(ErrorEnvelopeMixin, APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        self.admin = User.objects.create_user("admin")
        OrgMembership.objects.create(
            user=self.admin,
            organization=self.organization,
            role=OrgMembership.Role.ADMIN,
        )
        force_mfa(self.admin)
        self.client.force_authenticate(user=self.admin)

    def test_duplicate_agent_name_uses_the_envelope(self):
        message = "An agent with this name already exists in this organization."
        payload = {"name": "shopper", "organization": str(self.organization.id)}
        response = self.client.post("/v1/agents/", payload, format="json")
        self.assert_error_envelope(
            response,
            status_code=400,
            code=ErrorCode.BAD_REQUEST.value,
            message=message,
        )

    def test_agent_create_integrity_error_uses_the_envelope(self):
        message = "An agent with this name already exists in this organization."
        payload = {"name": "new-agent", "organization": str(self.organization.id)}
        with mock.patch(
            "apps.agents.views.Agent.create_with_key",
            side_effect=IntegrityError("duplicate"),
        ):
            response = self.client.post("/v1/agents/", payload, format="json")
        self.assert_error_envelope(
            response,
            status_code=400,
            code=ErrorCode.BAD_REQUEST.value,
            message=message,
        )

    def test_revoke_without_active_key_uses_the_envelope(self):
        url = f"/v1/agents/{self.agent.id}/revoke-key/"
        self.assertEqual(self.client.post(url).status_code, 200)
        response = self.client.post(url)
        self.assert_error_envelope(
            response,
            status_code=400,
            code=ErrorCode.BAD_REQUEST.value,
            message="No active API key to revoke.",
        )


class PolicyErrorEnvelopeTests(ErrorEnvelopeMixin, APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(
            agent=self.agent, weekly_budget_minor=123_400
        )
        self.rule = MerchantRule.objects.create(
            policy=self.policy,
            merchant_ref="acme.com",
            kind=MerchantRule.Kind.ALLOW,
        )
        self.admin = User.objects.create_user("admin")
        OrgMembership.objects.create(
            user=self.admin,
            organization=self.organization,
            role=OrgMembership.Role.ADMIN,
        )
        force_mfa(self.admin)
        self.client.force_authenticate(user=self.admin)

    def test_create_failures_use_the_envelope(self):
        cases = [
            (
                PolicyConflictError("Policy could not be created."),
                409,
                ErrorCode.BAD_REQUEST.value,
            ),
            (
                PolicyValidationError("Policy validation failed."),
                400,
                ErrorCode.VALIDATION_ERROR.value,
            ),
        ]
        for exc, status_code, code in cases:
            with self.subTest(exc=exc.__class__.__name__):
                with mock.patch(
                    "apps.policies.views.create_policy_version", side_effect=exc
                ):
                    response = self.client.post(
                        "/v1/policies/",
                        {"agent": str(self.agent.id)},
                        format="json",
                    )
                self.assert_error_envelope(
                    response,
                    status_code=status_code,
                    code=code,
                    message=str(exc),
                )

    def test_patch_failures_use_the_envelope(self):
        cases = [
            (
                PolicyConflictError("Policy changed concurrently."),
                409,
                ErrorCode.BAD_REQUEST.value,
            ),
            (
                PolicyValidationError("Policy is invalid."),
                400,
                ErrorCode.VALIDATION_ERROR.value,
            ),
        ]
        for exc, status_code, code in cases:
            with self.subTest(exc=exc.__class__.__name__):
                with mock.patch(
                    "apps.policies.views.create_policy_update", side_effect=exc
                ):
                    response = self.client.patch(
                        f"/v1/policies/{self.policy.id}/",
                        {"expected_version": 1},
                        format="json",
                    )
                self.assert_error_envelope(
                    response,
                    status_code=status_code,
                    code=code,
                    message=str(exc),
                )

    def test_merchant_rule_add_failures_use_the_envelope(self):
        cases = [
            (
                PolicyConflictError("Policy changed concurrently."),
                409,
                ErrorCode.BAD_REQUEST.value,
            ),
            (
                PolicyValidationError("Merchant rule is invalid."),
                400,
                ErrorCode.VALIDATION_ERROR.value,
            ),
        ]
        for exc, status_code, code in cases:
            with self.subTest(exc=exc.__class__.__name__):
                with mock.patch(
                    "apps.policies.views.add_merchant_rule", side_effect=exc
                ):
                    response = self.client.post(
                        f"/v1/policies/{self.policy.id}/merchant-rules/",
                        {
                            "expected_version": 1,
                            "merchant_ref": "new.com",
                            "kind": "allow",
                        },
                        format="json",
                    )
                self.assert_error_envelope(
                    response,
                    status_code=status_code,
                    code=code,
                    message=str(exc),
                )

    def test_merchant_rule_delete_failures_use_the_envelope(self):
        url = f"/v1/policies/{self.policy.id}/merchant-rules/{self.rule.id}/"
        cases = [
            (
                "missing If-Match",
                {},
                None,
                428,
                ErrorCode.PRECONDITION_REQUIRED.value,
                "Missing expected-version concurrency token; send the latest "
                "policy version in the If-Match header.",
                {},
            ),
            (
                "invalid If-Match",
                {"HTTP_IF_MATCH": "not-a-number"},
                None,
                400,
                ErrorCode.VALIDATION_ERROR.value,
                "If-Match must contain the latest policy version as a positive integer.",
                {"If-Match": ["Enter a positive integer."]},
            ),
            (
                "conflict",
                {"HTTP_IF_MATCH": "1"},
                PolicyConflictError("Policy changed concurrently."),
                409,
                ErrorCode.BAD_REQUEST.value,
                "Policy changed concurrently.",
                {},
            ),
            (
                "validation",
                {"HTTP_IF_MATCH": "1"},
                PolicyValidationError("Rule cannot be removed."),
                400,
                ErrorCode.VALIDATION_ERROR.value,
                "Rule cannot be removed.",
                {},
            ),
        ]
        for name, headers, exc, status_code, code, message, details in cases:
            with self.subTest(case=name):
                stack = ExitStack()
                if exc is not None:
                    stack.enter_context(
                        mock.patch(
                            "apps.policies.views.remove_merchant_rule",
                            side_effect=exc,
                        )
                    )
                with stack:
                    response = self.client.delete(url, **headers)
                self.assert_error_envelope(
                    response,
                    status_code=status_code,
                    code=code,
                    message=message,
                    details=details,
                )


@override_settings(PAYPAL_WEBHOOK_ID="webhook-id")
class WebhookErrorEnvelopeTests(ErrorEnvelopeMixin, APITestCase):
    def setUp(self):
        self.http = Client()

    def _post(
        self,
        *,
        event=None,
        headers=None,
        body=None,
        content_type="application/json",
    ):
        payload = (
            body
            if body is not None
            else json.dumps(event if event is not None else payout_event())
        )
        return self.http.post(
            "/webhooks/paypal",
            data=payload,
            content_type=content_type,
            **(SIGNATURE_HEADERS if headers is None else headers),
        )

    def test_webhook_failures_use_the_envelope(self):
        missing_signature = dict(SIGNATURE_HEADERS)
        missing_signature.pop("HTTP_PAYPAL_TRANSMISSION_SIG")
        cases = [
            {
                "name": "body too large",
                "body": "x" * (MAX_WEBHOOK_BYTES + 1),
                "status": 400,
                "code": ErrorCode.REQUEST_TOO_LARGE.value,
                "message": "The request body is too large.",
            },
            {
                "name": "wrong content type",
                "content_type": "text/plain",
                "status": 400,
                "code": ErrorCode.UNSUPPORTED_MEDIA_TYPE.value,
                "message": "Expected an application/json body.",
            },
            {
                "name": "invalid json",
                "body": "{not-json",
                "status": 400,
                "code": ErrorCode.INVALID_JSON.value,
                "message": "The request body is not valid JSON.",
            },
            {
                "name": "non-object event",
                "body": "[]",
                "status": 400,
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "The webhook event must be a JSON object.",
            },
            {
                "name": "missing event id",
                "event": {"event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED"},
                "status": 400,
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "The webhook event is missing an id.",
            },
            {
                "name": "missing event type",
                "event": {"id": "WH-1"},
                "status": 400,
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "The webhook event is missing a type.",
            },
            {
                "name": "event fields too long",
                "event": {
                    "id": "x" * 101,
                    "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
                },
                "status": 400,
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "The webhook event fields are too long.",
            },
            {
                "name": "missing signature headers",
                "headers": missing_signature,
                "status": 400,
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "The webhook signature headers are missing.",
            },
            {
                "name": "webhook id not configured",
                "webhook_id": "",
                "status": 503,
                "code": ErrorCode.SERVICE_UNAVAILABLE.value,
                "message": "Webhook verification is not configured.",
            },
            {
                "name": "client configuration invalid",
                "client_error": "configuration",
                "status": 503,
                "code": ErrorCode.SERVICE_UNAVAILABLE.value,
                "message": "Webhook verification is not configured.",
            },
            {
                "name": "verification not authorized",
                "client": StubVerifyClient(
                    error=PayPalResponseError("bad", status_code=401, code="AUTH")
                ),
                "status": 503,
                "code": ErrorCode.SERVICE_UNAVAILABLE.value,
                "message": "Webhook verification is unavailable.",
            },
            {
                "name": "verification transient failure",
                "client": StubVerifyClient(error=PayPalTransientError("down")),
                "status": 503,
                "code": ErrorCode.SERVICE_UNAVAILABLE.value,
                "message": "Webhook verification is unavailable.",
            },
            {
                "name": "signature not verified",
                "client": StubVerifyClient(status="FAILURE"),
                "status": 400,
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "The webhook signature could not be verified.",
            },
            {
                "name": "verification rejected",
                "client": StubVerifyClient(
                    error=PayPalResponseError("bad", status_code=422, code="BAD")
                ),
                "status": 400,
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "The webhook signature could not be verified.",
            },
        ]
        for case in cases:
            with self.subTest(case=case["name"]):
                with ExitStack() as stack:
                    if "webhook_id" in case:
                        stack.enter_context(
                            override_settings(PAYPAL_WEBHOOK_ID=case["webhook_id"])
                        )
                    client_patch = stack.enter_context(
                        mock.patch("apps.payments.views.build_paypal_client")
                    )
                    if case.get("client_error") == "configuration":
                        from apps.payments.paypal import PayPalConfigurationError

                        client_patch.side_effect = PayPalConfigurationError("bad")
                    else:
                        client_patch.return_value = case.get("client")
                    response = self._post(
                        event=case.get("event"),
                        headers=case.get("headers"),
                        body=case.get("body"),
                        content_type=case.get("content_type", "application/json"),
                    )
                self.assert_error_envelope(
                    response,
                    status_code=case["status"],
                    code=case["code"],
                    message=case["message"],
                )
