from allauth.account import urls as allauth_account_urls
from allauth.headless import urls as allauth_headless_urls
from allauth.mfa import urls as allauth_mfa_urls
from allauth.socialaccount import urls as allauth_socialaccount_urls
from allauth.socialaccount.providers.github import urls as github_urls
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import RequestDataTooBig
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views import defaults
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.errors import ErrorCode, ensure_request_id, error_payload
from apps.payments.settings_views import (
    PayPalSettingsProbeView,
    PayPalSettingsStatusView,
)
from apps.payments.views import paypal_webhook


def _api_error(request, *, status, code, message):
    response = JsonResponse(
        error_payload(request, code=code, message=message), status=status
    )
    response["X-Request-Id"] = ensure_request_id(request)
    return response


def health(request):
    return JsonResponse({"status": "ok"})


def ready(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def bad_request(request, exception):
    if request.path.startswith(("/v1/", "/api/")):
        too_large = isinstance(exception, RequestDataTooBig)
        return _api_error(
            request,
            status=400,
            code=ErrorCode.REQUEST_TOO_LARGE if too_large else ErrorCode.BAD_REQUEST,
            message=(
                "The request body is too large."
                if too_large
                else "The request could not be processed."
            ),
        )
    return defaults.bad_request(request, exception)


def permission_denied(request, exception):
    if request.path.startswith(("/v1/", "/api/")):
        return _api_error(
            request,
            status=403,
            code=ErrorCode.PERMISSION_DENIED,
            message="You do not have permission to perform this action.",
        )
    return defaults.permission_denied(request, exception)


def not_found(request, exception):
    if request.path.startswith(("/v1/", "/api/")):
        return _api_error(
            request,
            status=404,
            code=ErrorCode.NOT_FOUND,
            message="Not found.",
        )
    return defaults.page_not_found(request, exception)


def server_error(request):
    if request.path.startswith(("/v1/", "/api/")):
        return _api_error(
            request,
            status=500,
            code=ErrorCode.INTERNAL_ERROR,
            message="An internal error occurred.",
        )
    return defaults.server_error(request)


handler400 = bad_request
handler403 = permission_denied
handler404 = not_found
handler500 = server_error


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
    path("webhooks/paypal", paypal_webhook, name="paypal-webhook"),
    path("v1/", include("apps.spend.urls")),
    path("v1/", include("apps.approvals.urls")),
    path("v1/", include("apps.audit.urls")),
    path("v1/", include("apps.policies.urls")),
    path("v1/", include("apps.agents.urls")),
    path("v1/", include("apps.payments.urls")),
    path("api/settings/paypal/status/", PayPalSettingsStatusView.as_view(), name="settings-paypal-status"),
    path("api/settings/paypal/probe/", PayPalSettingsProbeView.as_view(), name="settings-paypal-probe"),
    path("api-auth/", include("rest_framework.urls")),
]
