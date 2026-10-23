from django.conf import settings
from django.contrib import admin
from django.core.exceptions import RequestDataTooBig
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views import defaults
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.errors import ErrorCode, ensure_request_id, error_payload


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


urlpatterns = [
    path(settings.ADMIN_PATH, admin.site.urls),
    path("healthz", health),
    path("readyz", ready),
    path("api/health/", health),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("v1/", include("apps.spend.urls")),
    path("v1/", include("apps.approvals.urls")),
    path("v1/", include("apps.audit.urls")),
    path("v1/", include("apps.policies.urls")),
    path("api-auth/", include("rest_framework.urls")),
]
