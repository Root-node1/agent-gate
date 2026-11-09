from django.contrib.auth import logout as django_logout
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status, views
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response

from .models import AccountProfile
from .permissions import IsAuthenticatedOr401
from .serializers import AccountProfileSerializer, CurrentUserSerializer


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
