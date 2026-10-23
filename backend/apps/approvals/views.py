from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import OrgMembership
from apps.accounts.permissions import IsApprover
from apps.common.errors import ApiError, ErrorCode
from apps.common.pagination import DashboardPagination
from apps.common.schema import error_responses

from . import services
from .models import Approval
from .serializers import ApprovalSerializer, DecisionSerializer


def approval_queryset(user):
    return Approval.objects.filter(
        organization__memberships__user=user,
        organization__memberships__role__in=(
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.APPROVER,
        ),
    ).select_related("organization", "approver", "spend_request__agent")


class ApprovalListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsApprover]

    @extend_schema(
        responses={200: ApprovalSerializer(many=True), **error_responses(400, 401, 403, 429)},
        summary="List approvals",
    )
    def get(self, request):
        outcome = request.query_params.get("outcome", Approval.Outcome.PENDING)
        if outcome != "all" and outcome not in Approval.Outcome.values:
            raise ApiError(
                "outcome must be pending, approved, denied, expired, or all.",
                code=ErrorCode.VALIDATION_ERROR,
                details={"outcome": ["Select a valid outcome."]},
            )
        queryset = approval_queryset(request.user)
        if outcome != "all":
            queryset = queryset.filter(outcome=outcome)
        paginator = DashboardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(ApprovalSerializer(page, many=True).data)


class ApprovalDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsApprover]

    @extend_schema(
        responses={200: ApprovalSerializer, **error_responses(401, 403, 404, 429)},
        summary="Get an approval",
    )
    def get(self, request, pk):
        approval = get_object_or_404(approval_queryset(request.user), pk=pk)
        return Response(ApprovalSerializer(approval).data)


class DecisionMixin:
    def _decide(self, request, pk, *, approve):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            approval, _ = services.decide(
                pk,
                user=request.user,
                approve=approve,
                note=serializer.validated_data["note"],
            )
        except services.ApprovalNotFound as exc:
            raise ApiError(
                "Approval not found.",
                code=ErrorCode.NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            ) from exc
        except services.ApprovalExpired as exc:
            raise ApiError(
                "This approval has expired.",
                code=ErrorCode.APPROVAL_EXPIRED,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        except services.ApprovalConflict as exc:
            raise ApiError(
                str(exc),
                code=ErrorCode.APPROVAL_CONFLICT,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        except services.ApprovalRecheckFailed as exc:
            raise ApiError(
                str(exc),
                code=ErrorCode.RECHECK_FAILED,
                status_code=status.HTTP_409_CONFLICT,
                details={"rules": exc.rules},
            ) from exc
        approval = get_object_or_404(approval_queryset(request.user), pk=approval.pk)
        return Response(ApprovalSerializer(approval).data)


class ApprovalApproveView(DecisionMixin, APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsApprover]

    @extend_schema(
        request=DecisionSerializer,
        responses={200: ApprovalSerializer, **error_responses(400, 401, 403, 404, 409, 429)},
        summary="Approve a pending request after a recheck",
    )
    def post(self, request, pk):
        return self._decide(request, pk, approve=True)


class ApprovalDenyView(DecisionMixin, APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsApprover]

    @extend_schema(
        request=DecisionSerializer,
        responses={200: ApprovalSerializer, **error_responses(400, 401, 403, 404, 409, 429)},
        summary="Deny a pending request",
    )
    def post(self, request, pk):
        return self._decide(request, pk, approve=False)
