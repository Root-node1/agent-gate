from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from gate import auth_views


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/auth/csrf/", auth_views.csrf_token, name="auth-csrf"),
    path("api/auth/options/", auth_views.auth_options, name="auth-options"),
    path("api/auth/session/", auth_views.session_status, name="auth-session"),
    path("api/auth/login/", auth_views.session_login, name="auth-login"),
    path("api/auth/logout/", auth_views.session_logout, name="auth-logout"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("v1/", include("gate.urls")),
]

if settings.GOOGLE_OAUTH_ENABLED:
    urlpatterns.append(path("accounts/", include("allauth.urls")))
else:
    urlpatterns.append(path("accounts/google/login/", auth_views.google_oauth_unavailable))
