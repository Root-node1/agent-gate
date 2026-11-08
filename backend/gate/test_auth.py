import json
import re
import time
from urllib.parse import parse_qs, urlparse

from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal.auth import (
    TOTP,
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
)
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.test.utils import override_settings

from gate.models import AccountProfile

HEADLESS = "/api/auth/_allauth/browser/v1"


class DashboardAuthTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="operator",
            email="operator@example.com",
            password="strong-password",
        )
        EmailAddress.objects.create(
            user=self.user,
            email="operator@example.com",
            verified=True,
            primary=True,
        )

    def csrf_token(self, client):
        return client.get("/api/auth/csrf/").json()["csrfToken"]

    def post_json(self, client, path, body):
        return client.post(
            path,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(client),
        )

    def test_public_session_endpoint_reports_anonymous(self):
        response = self.client.get("/api/auth/session/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"authenticated": False})

    def test_legacy_login_endpoint_is_not_available(self):
        self.assertEqual(self.client.post("/api/auth/login/").status_code, 404)

    def test_headless_login_requires_csrf_and_authenticates_verified_email(self):
        client = Client(enforce_csrf_checks=True)
        path = f"{HEADLESS}/auth/login"
        body = {"email": "operator@example.com", "password": "strong-password"}
        rejected = client.post(
            path, data=json.dumps(body), content_type="application/json"
        )
        self.assertEqual(rejected.status_code, 403)

        response = self.post_json(client, path, body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["meta"]["is_authenticated"])
        self.assertTrue(client.get("/api/auth/session/").json()["authenticated"])

    def test_headless_login_does_not_authenticate_invalid_credentials(self):
        client = Client(enforce_csrf_checks=True)
        response = self.post_json(
            client,
            f"{HEADLESS}/auth/login",
            {"email": "operator@example.com", "password": "wrong-password"},
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(client.get("/api/auth/session/").json()["authenticated"])

    def test_headless_login_requires_totp_when_authenticator_is_enrolled(self):
        secret = generate_totp_secret()
        TOTP.activate(self.user, secret)
        client = Client(enforce_csrf_checks=True)
        login_response = self.post_json(
            client,
            f"{HEADLESS}/auth/login",
            {"email": "operator@example.com", "password": "strong-password"},
        )
        self.assertEqual(login_response.status_code, 401)
        self.assertFalse(login_response.json()["meta"]["is_authenticated"])
        self.assertTrue(
            any(
                flow["id"] == "mfa_authenticate" and flow.get("is_pending")
                for flow in login_response.json()["data"]["flows"]
            )
        )

        code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
        mfa_response = self.post_json(
            client,
            f"{HEADLESS}/auth/2fa/authenticate",
            {"code": code},
        )
        self.assertEqual(mfa_response.status_code, 200)
        self.assertTrue(mfa_response.json()["meta"]["is_authenticated"])
        self.assertTrue(client.get("/api/auth/session/").json()["authenticated"])

    def test_authenticated_user_can_enroll_totp_and_generate_recovery_codes(self):
        client = Client(enforce_csrf_checks=True)
        self.post_json(
            client,
            f"{HEADLESS}/auth/login",
            {"email": "operator@example.com", "password": "strong-password"},
        )

        setup = client.get(f"{HEADLESS}/account/authenticators/totp")
        self.assertEqual(setup.status_code, 404)
        secret = setup.json()["meta"]["secret"]
        code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
        activated = self.post_json(
            client,
            f"{HEADLESS}/account/authenticators/totp",
            {"code": code},
        )
        self.assertEqual(activated.status_code, 401)
        self.assertIn(
            "reauthenticate",
            [flow["id"] for flow in activated.json()["data"]["flows"]],
        )
        reauthenticated = self.post_json(
            client,
            f"{HEADLESS}/auth/reauthenticate",
            {"password": "strong-password"},
        )
        self.assertEqual(reauthenticated.status_code, 200)
        activated = self.post_json(
            client,
            f"{HEADLESS}/account/authenticators/totp",
            {"code": code},
        )
        self.assertEqual(activated.status_code, 200)
        self.assertEqual(activated.json()["data"]["type"], "totp")

        generated = self.post_json(
            client,
            f"{HEADLESS}/account/authenticators/recovery-codes",
            {},
        )
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(len(generated.json()["data"]["unused_codes"]), 10)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_email_uses_frontend_route_and_key(self):
        client = Client(enforce_csrf_checks=True)
        requested = self.post_json(
            client,
            f"{HEADLESS}/auth/password/request",
            {"email": "operator@example.com"},
        )
        self.assertEqual(requested.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"/reset-password/([^\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(link, mail.outbox[0].body)
        key = link.group(1).rstrip(".")

        checked = client.get(
            f"{HEADLESS}/auth/password/reset",
            HTTP_X_PASSWORD_RESET_KEY=key,
        )
        self.assertEqual(checked.status_code, 200)
        reset = self.post_json(
            client,
            f"{HEADLESS}/auth/password/reset",
            {"key": key, "password": "Even-stronger-Passphrase-2030!"},
        )
        self.assertEqual(reset.status_code, 401)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Even-stronger-Passphrase-2030!"))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_headless_signup_persists_profile_and_sends_verification(self):
        client = Client(enforce_csrf_checks=True)
        response = self.post_json(
            client,
            f"{HEADLESS}/auth/signup",
            {
                "email": "new-operator@example.com",
                "password": "strong-password",
                "full_name": "  Morgan   Agent  ",
                "organization": "  Example Labs  ",
                "accept_terms": True,
            },
        )
        self.assertEqual(response.status_code, 401)
        user = get_user_model().objects.get(email="new-operator@example.com")
        profile = AccountProfile.objects.get(user=user)
        self.assertEqual(user.get_full_name(), "Morgan Agent")
        self.assertEqual(profile.full_name, "Morgan Agent")
        self.assertEqual(profile.organization, "Example Labs")
        self.assertIsNotNone(profile.terms_accepted_at)
        self.assertFalse(client.get("/api/auth/session/").json()["authenticated"])
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b", mail.outbox[0].body)
        self.assertIsNotNone(code, mail.outbox[0].body)

        verified = self.post_json(
            client,
            f"{HEADLESS}/auth/email/verify",
            {"key": code.group(1)},
        )
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(EmailAddress.objects.get(user=user).verified)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ACCOUNT_RATE_LIMITS={"confirm_email": None},
    )
    def test_verification_code_can_be_resent_and_email_changed(self):
        client = Client(enforce_csrf_checks=True)
        signup = self.post_json(
            client,
            f"{HEADLESS}/auth/signup",
            {
                "email": "pending@example.com",
                "password": "strong-password",
                "full_name": "Morgan Agent",
                "organization": "Example Labs",
                "accept_terms": True,
            },
        )
        self.assertEqual(signup.status_code, 401)

        resend = client.post(
            f"{HEADLESS}/auth/email/verify/resend",
            HTTP_X_CSRFTOKEN=self.csrf_token(client),
        )
        self.assertEqual(resend.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)

        changed = self.post_json(
            client,
            f"{HEADLESS}/account/email",
            {"email": "updated@example.com"},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertTrue(
            EmailAddress.objects.filter(email="updated@example.com").exists()
        )

    def test_headless_signup_requires_terms_acceptance(self):
        response = self.post_json(
            self.client,
            f"{HEADLESS}/auth/signup",
            {
                "email": "no-terms@example.com",
                "password": "strong-password",
                "full_name": "Morgan Agent",
                "organization": "Example Labs",
            },
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(
            get_user_model().objects.filter(email="no-terms@example.com").exists()
        )

    def test_headless_browser_config_and_mfa_routes_are_available(self):
        config = self.client.get(f"{HEADLESS}/config")
        self.assertEqual(config.status_code, 200)
        self.assertTrue(config.json()["data"]["account"]["is_open_for_signup"])

        session = self.client.get(f"{HEADLESS}/auth/session")
        self.assertEqual(session.status_code, 401)

        authenticator = self.client.get(f"{HEADLESS}/account/authenticators/totp")
        self.assertEqual(authenticator.status_code, 401)

    def test_remember_session_only_changes_an_authenticated_session(self):
        client = Client(enforce_csrf_checks=True)
        response = self.post_json(
            client,
            "/api/auth/session/remember/",
            {"remember": True},
        )
        self.assertEqual(response.status_code, 401)

        self.post_json(
            client,
            f"{HEADLESS}/auth/login",
            {"email": "operator@example.com", "password": "strong-password"},
        )
        response = self.post_json(
            client,
            "/api/auth/session/remember/",
            {"remember": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.session.get_expiry_age(), 60 * 60 * 24 * 30)

    @override_settings(GOOGLE_OAUTH_ENABLED=False)
    def test_auth_options_report_oauth_configuration_without_credentials(self):
        response = self.client.get("/api/auth/options/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["googleOAuthEnabled"])
        self.assertFalse(response.json()["githubOAuthEnabled"])
        self.assertTrue(response.json()["csrfToken"])

    @override_settings(GOOGLE_OAUTH_ENABLED=True)
    def test_auth_options_do_not_expose_oauth_credentials(self):
        response = self.client.get("/api/auth/options/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["googleOAuthEnabled"])
        self.assertNotIn("client", response.content.decode().lower())

    def test_google_login_returns_service_unavailable_when_not_configured(self):
        response = self.client.get("/accounts/google/login/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Google sign-in is not configured on this server."},
        )

    def test_github_login_returns_service_unavailable_when_not_configured(self):
        response = self.client.get("/accounts/github/login/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "GitHub sign-in is not configured on this server."},
        )

    def test_google_login_starts_with_csrf_protected_post(self):
        client = Client(enforce_csrf_checks=True)
        csrf = self.csrf_token(client)
        with override_settings(
            ROOT_URLCONF="allauth.urls",
            SOCIALACCOUNT_PROVIDERS={
                "google": {
                    "SCOPE": ["profile", "email"],
                    "OAUTH_PKCE_ENABLED": True,
                    "APPS": [
                        {
                            "client_id": "test-client-id",
                            "secret": "test-secret",
                            "key": "",
                        }
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
