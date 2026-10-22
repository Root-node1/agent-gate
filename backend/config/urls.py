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
