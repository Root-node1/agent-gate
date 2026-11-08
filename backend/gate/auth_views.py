from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_POST


@require_GET
def csrf_token(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_GET
def auth_options(request):
    return JsonResponse(
        {
            "csrfToken": get_token(request),
            "googleOAuthEnabled": settings.GOOGLE_OAUTH_ENABLED,
            "githubOAuthEnabled": settings.GITHUB_OAUTH_ENABLED,
        }
    )


@require_GET
def google_oauth_unavailable(request):
    return JsonResponse(
        {"detail": "Google sign-in is not configured on this server."},
        status=503,
    )


@require_GET
def github_oauth_unavailable(request):
    return JsonResponse(
        {"detail": "GitHub sign-in is not configured on this server."},
        status=503,
    )


@require_GET
def session_status(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"authenticated": False})
    return JsonResponse({"authenticated": True, "user": {"username": user.get_username()}})


@require_POST
def session_logout(request):
    logout(request)
    return JsonResponse({"authenticated": False})
