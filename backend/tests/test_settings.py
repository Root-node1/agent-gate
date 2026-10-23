from django.test import TestCase, override_settings

EXEMPT = [r"^healthz$", r"^readyz$"]


@override_settings(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=EXEMPT)
class RedirectExemptionTests(TestCase):
    def test_health_endpoints_are_not_redirected(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/readyz").status_code, 200)

    def test_other_paths_redirect_to_https(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))
