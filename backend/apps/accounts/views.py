from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status, views
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import AccountProfile
from .permissions import IsAuthenticatedOr401
from .serializers import AccountProfileSerializer, CurrentUserSerializer


class CsrfTokenView(views.APIView):
    """Return a CSRF token for the SPA to include in X-CSRFToken headers."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: {"type": "object", "properties": {"csrfToken": {"type": "string"}}}})
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class AuthOptionsView(views.APIView):
    """Return OAuth provider enablement flags and CSRF token for the login page."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        responses={
            200: {
                "type": "object",
                "properties": {
                    "csrfToken": {"type": "string"},
                    "googleOAuthEnabled": {"type": "boolean"},
                    "githubOAuthEnabled": {"type": "boolean"},
                },
            }
        }
    )
    def get(self, request):
        return Response(
            {
                "csrfToken": get_token(request),
                "googleOAuthEnabled": settings.GOOGLE_OAUTH_ENABLED,
                "githubOAuthEnabled": settings.GITHUB_OAUTH_ENABLED,
            }
        )


class SessionStatusView(views.APIView):
    """Return whether the current session is authenticated.

    Unlike ``/api/auth/user/`` (401 when unauthenticated), this endpoint
    always returns 200 with an ``authenticated`` boolean so the SPA can
    restore session state without treating 401 as an error.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: {
                "type": "object",
                "properties": {
                    "authenticated": {"type": "boolean"},
                    "user": {
                        "type": "object",
                        "properties": {"username": {"type": "string"}},
                    },
                },
            }
        }
    )
    def get(self, request):
        user = request.user
        if user and user.is_authenticated:
            return Response(
                {"authenticated": True, "user": {"username": user.get_username()}}
            )
        return Response({"authenticated": False})


class SessionRememberView(views.APIView):
    """Set session expiry based on the remember-me flag."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticatedOr401]

    def handle_exception(self, exc):
        if isinstance(exc, exceptions.NotAuthenticated):
            return Response(
                {"detail": exc.detail},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return super().handle_exception(exc)

    @extend_schema(
        request={"type": "object", "properties": {"remember": {"type": "boolean"}}},
        responses={200: {"type": "object", "properties": {"remember": {"type": "boolean"}}}},
    )
    def post(self, request):
        remember = request.data.get("remember")
        if not isinstance(remember, bool):
            return Response(
                {"detail": "A boolean remember value is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if remember:
            request.session.set_expiry(60 * 60 * 24 * 30)
        else:
            request.session.set_expiry(0)
        return Response({"remember": remember})


class CurrentUserView(views.APIView):
    """Authenticated dashboard user. Reads only the session; agent API keys are rejected."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticatedOr401]

    def handle_exception(self, exc):
        # Don't coerce NotAuthenticated to 403 when there's no WWW-Authenticate header.
        # We want 401 for unauthenticated API requests.
        if isinstance(exc, exceptions.NotAuthenticated):
            return Response(
                {"detail": exc.detail},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return super().handle_exception(exc)

    @extend_schema(responses=CurrentUserSerializer)
    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)


class ProfileView(views.APIView):
    """Read and update the authenticated user's display profile.

    Only ``full_name`` is editable. Organization membership and roles are
    managed through Organization and OrgMembership, never through this
    endpoint.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticatedOr401]

    def handle_exception(self, exc):
        if isinstance(exc, exceptions.NotAuthenticated):
            return Response(
                {"detail": exc.detail},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return super().handle_exception(exc)

    @extend_schema(responses=AccountProfileSerializer)
    def get(self, request):
        profile, _ = AccountProfile.objects.get_or_create(user=request.user)
        return Response(AccountProfileSerializer(profile).data)

    @extend_schema(request=AccountProfileSerializer, responses=AccountProfileSerializer)
    def patch(self, request):
        profile, _ = AccountProfile.objects.get_or_create(user=request.user)
        serializer = AccountProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class LogoutView(views.APIView):
    """Destroy the dashboard session. CSRF-protected via SessionAuthentication."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticatedOr401]

    def handle_exception(self, exc):
        if isinstance(exc, exceptions.NotAuthenticated):
            return Response(
                {"detail": exc.detail},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return super().handle_exception(exc)

    @extend_schema(responses={status.HTTP_204_NO_CONTENT: None})
    def post(self, request):
        django_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
