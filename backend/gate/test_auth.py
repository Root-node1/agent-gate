import json
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.test.utils import override_settings


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

    @override_settings(GOOGLE_OAUTH_ENABLED=False)
    def test_auth_options_report_google_oauth_as_disabled_without_credentials(self):
        response = self.client.get("/api/auth/options/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["googleOAuthEnabled"])
        self.assertTrue(response.json()["csrfToken"])

    @override_settings(GOOGLE_OAUTH_ENABLED=True)
    def test_auth_options_report_google_oauth_as_enabled_without_exposing_credentials(self):
        response = self.client.get("/api/auth/options/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["googleOAuthEnabled"])
        self.assertNotIn("client", response.content.decode().lower())

    @override_settings(GOOGLE_OAUTH_ENABLED=False)
    def test_google_login_returns_service_unavailable_when_not_configured(self):
        response = self.client.get("/accounts/google/login/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Google sign-in is not configured on this server."},
        )

    def test_google_login_starts_with_csrf_protected_post(self):
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf/").json()["csrfToken"]
        with override_settings(
            ROOT_URLCONF="allauth.urls",
            SOCIALACCOUNT_PROVIDERS={
                "google": {
                    "SCOPE": ["profile", "email"],
                    "OAUTH_PKCE_ENABLED": True,
                    "APPS": [
                        {"client_id": "test-client-id", "secret": "test-secret", "key": ""}
                    ],
                }
            },
            SOCIALACCOUNT_LOGIN_ON_GET=False,
            LOGIN_REDIRECT_URL="/app",
        ):
            response = client.post(
                "/google/login/",
                {"csrfmiddlewaretoken": csrf, "process": "login"},
            )
            csrf_rejected = Client(enforce_csrf_checks=True).post(
                "/google/login/",
                {"process": "login"},
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts.google.com", response["Location"])
        redirect_uri = parse_qs(urlparse(response["Location"]).query)["redirect_uri"][0]
        self.assertIn("/google/login/callback/", redirect_uri)
        self.assertEqual(csrf_rejected.status_code, 403)
