from django.conf import settings
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from allauth.account import urls as allauth_account_urls
from allauth.headless import urls as allauth_headless_urls


def health(request):
    return JsonResponse({"status": "ok"})


def ready(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def _without_password_change(patterns):
    """allauth bundles password-change routes (for logged-in users). AUTH-01 only
    ships signup, login, logout and email confirmation. Password reset routes are
    kept because the account adapter uses them for 'account already exists' emails.
    Password change is excluded to avoid exposing it prematurely (AUTH-03)."""
    return [
        pattern
        for pattern in patterns
        if not str(pattern.pattern).replace("^", "").startswith("password/change")
    ]


allauth_patterns = _without_password_change(allauth_account_urls.urlpatterns)

headless_patterns = allauth_headless_urls.urlpatterns


urlpatterns = [
    path(settings.ADMIN_PATH, admin.site.urls),
    path("healthz", health),
    path("readyz", ready),
    path("api/health/", health),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("accounts/", include(allauth_patterns)),
    path("api/auth/headless/", include(headless_patterns)),
    path("api/auth/", include("apps.accounts.urls")),
    path("v1/", include("apps.spend.urls")),
    path("v1/", include("apps.approvals.urls")),
    path("v1/", include("apps.audit.urls")),
    path("v1/", include("apps.policies.urls")),
    path("api-auth/", include("rest_framework.urls")),
]
