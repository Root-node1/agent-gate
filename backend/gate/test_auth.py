import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase


class DashboardAuthTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operator", password="strong-password")

    def test_public_session_endpoint_reports_anonymous(self):
        response = self.client.get("/api/auth/session/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"authenticated": False})

    def test_login_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            "/api/auth/login/",
            data=json.dumps({"username": "operator", "password": "strong-password"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_login_sets_authenticated_session_and_logout_clears_it(self):
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf/").json()["csrfToken"]
        login_response = client.post(
            "/api/auth/login/",
            data=json.dumps({"username": "operator", "password": "strong-password"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(
            login_response.json(),
            {"authenticated": True, "user": {"username": "operator"}},
        )
        self.assertEqual(client.get("/api/auth/session/").json()["authenticated"], True)

        csrf = client.get("/api/auth/csrf/").json()["csrfToken"]
        logout_response = client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json(), {"authenticated": False})
        self.assertEqual(client.get("/api/auth/session/").json(), {"authenticated": False})

    def test_invalid_credentials_do_not_create_session(self):
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf/").json()["csrfToken"]
        response = client.post(
            "/api/auth/login/",
            data=json.dumps({"username": "operator", "password": "wrong-password"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid username or password."})
        self.assertEqual(client.get("/api/auth/session/").json(), {"authenticated": False})

    def test_malformed_login_body_is_rejected(self):
        response = self.client.post(
            "/api/auth/login/",
            data="{",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
