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
    path("api/auth/session/remember/", auth_views.session_remember, name="auth-remember"),
    path("api/auth/logout/", auth_views.session_logout, name="auth-logout"),
    path("api/auth/_allauth/", include("allauth.headless.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("v1/", include("gate.urls")),
]

if not settings.GOOGLE_OAUTH_ENABLED:
    urlpatterns.append(path("accounts/google/login/", auth_views.google_oauth_unavailable))

if not settings.GITHUB_OAUTH_ENABLED:
    urlpatterns.append(path("accounts/github/login/", auth_views.github_oauth_unavailable))

urlpatterns.append(path("accounts/", include("allauth.urls")))
