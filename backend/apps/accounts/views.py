from django.contrib.auth import logout as django_logout

from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status, views
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response

from .permissions import IsAuthenticatedOr401
from .serializers import CurrentUserSerializer


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
