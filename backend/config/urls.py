from allauth.account import urls as allauth_account_urls
from allauth.headless import urls as allauth_headless_urls
from allauth.mfa import urls as allauth_mfa_urls
from allauth.socialaccount import urls as allauth_socialaccount_urls
from allauth.socialaccount.providers.github import urls as github_urls
from django.conf import settings
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(request):
    return JsonResponse({"status": "ok"})


def ready(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def _headless_only_account_patterns(patterns):
    """Allauth bundles HTML-form routes under ``/accounts/``. AUTH-01 mounts only
    the headless JSON endpoints at ``/api/auth/headless/`` as the SPA contract.

    The password-change form is excluded (not exposed prematurely; AUTH-03), and
    the non-headless password-reset forms (``password/reset/``, ``.../key/...``)
    are excluded too: they are redundant now that the Headless JSON contract
    exists and would otherwise present a competing form-based reset surface that
    bypasses the SPA's CSRF + link handling. The reset link email uses the
    ``HEADLESS_FRONTEND_URLS["account_reset_password"]`` SPA link instead of
    ``reverse("account_reset_password")``, so removing these routes is safe.
    """
    stripped = []
    for pattern in patterns:
        name = str(pattern.pattern).replace("^", "")
        if name.startswith("password/change") or name.startswith("password/reset"):
            continue
        stripped.append(pattern)
    return stripped


allauth_patterns = _headless_only_account_patterns(allauth_account_urls.urlpatterns)

headless_patterns = allauth_headless_urls.urlpatterns


urlpatterns = [
    path(settings.ADMIN_PATH, admin.site.urls),
    path("healthz", health),
    path("readyz", ready),
    path("api/health/", health),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("accounts/", include(allauth_patterns)),
    path("accounts/", include(github_urls)),
    path("3rdparty/", include(allauth_socialaccount_urls)),
    path("mfa/", include(allauth_mfa_urls)),
    path("api/auth/headless/", include(headless_patterns)),
    path("api/auth/", include("apps.accounts.urls")),
    path("v1/", include("apps.spend.urls")),
    path("v1/", include("apps.approvals.urls")),
    path("v1/", include("apps.audit.urls")),
    path("v1/", include("apps.policies.urls")),
    path("v1/", include("apps.agents.urls")),
    path("api-auth/", include("rest_framework.urls")),
]
