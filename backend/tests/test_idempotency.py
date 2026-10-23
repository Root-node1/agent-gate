from uuid import uuid4

from rest_framework.test import APITestCase

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.policies.models import Policy
from apps.spend.models import SpendRequest

URL = "/v1/spend-requests/"


class IdempotencyTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, key = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")

    def post(self, key, **overrides):
        body = {
            "amount": "10.00",
            "currency": "USD",
            "merchant": "acme.com",
            "source": "trusted",
        }
        body.update(overrides)
        return self.client.post(URL, body, format="json", HTTP_IDEMPOTENCY_KEY=key)

    def test_same_key_and_body_replays_the_stored_request(self):
        key = str(uuid4())
        first = self.post(key)
        second = self.post(key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(second["Idempotent-Replayed"], "true")
        self.assertEqual(SpendRequest.objects.count(), 1)

    def test_first_response_has_no_replay_header(self):
        response = self.post(str(uuid4()))
        self.assertNotIn("Idempotent-Replayed", response)

    def test_same_key_with_a_different_body_is_a_conflict(self):
        key = str(uuid4())
        self.post(key)
        conflict = self.post(key, amount="11.00")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(SpendRequest.objects.count(), 1)

    def test_same_key_with_a_different_destination_is_a_conflict(self):
        key = str(uuid4())
        self.post(key, destination_type="paypal_email", destination_value="a@example.com")
        conflict = self.post(
            key, destination_type="paypal_email", destination_value="b@example.com"
        )
        self.assertEqual(conflict.status_code, 409)

    def test_destination_normalization_does_not_break_replay(self):
        key = str(uuid4())
        first = self.post(
            key, destination_type="paypal_email", destination_value=" Seller@Example.com "
        )
        second = self.post(
            key, destination_type="paypal_email", destination_value="seller@example.com"
        )
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(second["Idempotent-Replayed"], "true")

    def test_destination_is_stored_normalized_with_a_fingerprint(self):
        response = self.post(
            str(uuid4()), destination_type="paypal_email", destination_value="Seller@Example.com "
        )
        self.assertEqual(response.status_code, 201)
        spend_request = SpendRequest.objects.get()
        self.assertEqual(spend_request.destination_value, "seller@example.com")
        self.assertEqual(len(spend_request.destination_fingerprint), 64)

    def test_destination_type_without_value_is_rejected(self):
        response = self.post(str(uuid4()), destination_type="paypal_email")
        self.assertEqual(response.status_code, 400)

    def test_missing_key_is_rejected(self):
        response = self.client.post(
            URL,
            {"amount": "10.00", "currency": "USD", "merchant": "acme.com", "source": "trusted"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_oversized_key_is_rejected(self):
        self.assertEqual(self.post("k" * 256).status_code, 400)
