import json
from json import JSONDecodeError

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
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
        }
    )


@require_GET
def google_oauth_unavailable(request):
    return JsonResponse(
        {"detail": "Google sign-in is not configured on this server."},
        status=503,
    )


@require_GET
def session_status(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"authenticated": False})
    return JsonResponse({"authenticated": True, "user": {"username": user.get_username()}})


@require_POST
def session_login(request):
    try:
        data = json.loads(request.body)
    except (JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Request body must be valid JSON."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"detail": "Request body must be a JSON object."}, status=400)

    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return JsonResponse({"detail": "Username and password are required."}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"detail": "Invalid username or password."}, status=401)

    login(request, user)
    return JsonResponse({"authenticated": True, "user": {"username": user.get_username()}})


@require_POST
def session_logout(request):
    logout(request)
    return JsonResponse({"authenticated": False})
