from uuid import uuid4

from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Organization, User
from apps.agents.models import Agent
from apps.policies.models import Policy
from apps.spend.models import SpendRequest

URL = "/v1/spend-requests/"


class ApiErrorTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, self.key = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key}")

    def post(self, **overrides):
        body = {
            "amount": "10.00",
            "currency": "USD",
            "merchant": "acme.com",
        }
        body.update(overrides)
        return self.client.post(
            URL, body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )

    def test_error_envelope_carries_the_request_id(self):
        response = self.post(amount="-5")
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["error"]["code"], "validation_error")
        self.assertEqual(body["request_id"], response["X-Request-Id"])

    def test_success_responses_carry_the_request_id_header(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response["X-Request-Id"]), 32)

    def test_unmatched_api_path_uses_the_envelope(self):
        response = self.client.get("/v1/not-a-route/")
        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["error"]["code"], "not_found")
        self.assertEqual(body["request_id"], response["X-Request-Id"])

    def test_client_supplied_request_id_is_not_echoed(self):
        response = self.client.post(
            URL,
            {
                "amount": "-5",
                "currency": "USD",
                "merchant": "acme.com",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_X_REQUEST_ID="attacker-controlled",
        )
        self.assertNotEqual(response["X-Request-Id"], "attacker-controlled")
        self.assertNotIn("attacker-controlled", response.content.decode())

    def test_error_details_do_not_echo_user_values(self):
        amount_response = self.post(amount="sk_live_super_secret")
        currency_response = self.post(currency="ZZZ")
        self.assertNotIn("sk_live_super_secret", amount_response.content.decode())
        self.assertNotIn("ZZZ", currency_response.content.decode())
        self.assertIn("amount", amount_response.json()["error"]["details"])
        self.assertIn("currency", currency_response.json()["error"]["details"])

    def test_unknown_and_revoked_keys_have_the_same_error(self):
        body = {
            "amount": "10.00",
            "currency": "USD",
            "merchant": "acme.com",
        }
        unknown = APIClient().post(
            URL,
            body,
            format="json",
            HTTP_AUTHORIZATION="Bearer agk_unknown_key",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.agent.api_keys.update(revoked_at=timezone.now())
        revoked = APIClient().post(
            URL,
            body,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.key}",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(revoked.status_code, 401)
        self.assertEqual(unknown.json()["error"], revoked.json()["error"])

    def test_suspended_agent_has_its_own_code(self):
        self.agent.status = Agent.Status.SUSPENDED
        self.agent.save(update_fields=["status", "updated_at"])
        response = self.post()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "agent_suspended")

    def test_missing_idempotency_key_is_validation_error(self):
        response = self.client.post(
            URL,
            {
                "amount": "10.00",
                "currency": "USD",
                "merchant": "acme.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "idempotency_key_required")

    def test_malformed_json_uses_the_envelope(self):
        response = self.client.post(
            URL,
            "{",
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_json")

    def test_unsupported_media_type_uses_the_envelope(self):
        response = self.client.post(
            URL,
            "not-json",
            content_type="text/plain",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["error"]["code"], "unsupported_media_type")

    def test_wrong_method_uses_the_envelope(self):
        response = self.client.delete(URL)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["code"], "method_not_allowed")

    def test_amount_requires_a_decimal_string(self):
        invalid = [
            10.0,
            "1e3",
            "+1.00",
            " 1.00",
            "1.",
            "1.001",
            "1000000000000.00",
            "0.00",
        ]
        for value in invalid:
            with self.subTest(value=value):
                response = self.post(amount=value)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["code"], "validation_error"
                )

    def test_zero_decimal_currency_rejects_a_fraction(self):
        response = self.post(amount="100.00", currency="JPY")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_valid_amount_with_fewer_decimal_places_is_allowed(self):
        response = self.post(amount="10.5")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(SpendRequest.objects.get().amount_minor, 1_050)

    def test_bidi_and_control_characters_are_removed(self):
        response = self.post(
            merchant="acme\u202e.com",
            purpose="pay\u202efoo\x00",
            evidence_excerpt="evidence\u202e\x07",
        )
        self.assertEqual(response.status_code, 201)
        spend_request = SpendRequest.objects.get()
        self.assertEqual(spend_request.merchant_ref, "acme.com")
        self.assertEqual(spend_request.purpose, "payfoo")
        self.assertEqual(spend_request.evidence_excerpt, "evidence")
        for value in (
            spend_request.merchant_ref,
            spend_request.purpose,
            spend_request.evidence_excerpt,
        ):
            self.assertNotIn("\u202e", value)
            self.assertNotIn("\x00", value)
            self.assertNotIn("\x07", value)

    def test_api_csrf_failure_uses_the_envelope(self):
        user = User.objects.create_user("approver")
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        response = client.post(
            f"/v1/approvals/{uuid4()}/approve/", {}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["error"]["code"], "permission_denied")
        self.assertEqual(body["request_id"], response["X-Request-Id"])
