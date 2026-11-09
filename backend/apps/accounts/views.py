from django.contrib.auth import logout as django_logout
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status, views
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response

from apps.common.errors import ApiError, ErrorCode, api_exception_handler

from .permissions import IsAuthenticatedOr401
from .serializers import CurrentUserSerializer


def _unauthenticated(request):
    """Return the shared 401 envelope without DRF's header-dependent 403 coercion."""
    return api_exception_handler(
        ApiError(
            "Authentication failed.",
            code=ErrorCode.AUTHENTICATION_FAILED,
            status_code=status.HTTP_401_UNAUTHORIZED,
        ),
        {"request": request},
    )


class CurrentUserView(views.APIView):
    """Authenticated dashboard user. Reads only the session; agent API keys are rejected."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticatedOr401]

    def handle_exception(self, exc):
        # Don't coerce NotAuthenticated to 403 when there's no WWW-Authenticate header.
        # We want 401 for unauthenticated API requests.
        if isinstance(exc, exceptions.NotAuthenticated):
            return _unauthenticated(self.request)
        return super().handle_exception(exc)

    @extend_schema(responses=CurrentUserSerializer)
    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)


class LogoutView(views.APIView):
    """Destroy the dashboard session. CSRF-protected via SessionAuthentication."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticatedOr401]

    def handle_exception(self, exc):
        if isinstance(exc, exceptions.NotAuthenticated):
            return _unauthenticated(self.request)
        return super().handle_exception(exc)

    @extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    def post(self, request):
        django_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
