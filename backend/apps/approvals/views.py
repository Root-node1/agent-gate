from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import OrgMembership
from apps.accounts.permissions import IsApprover
from apps.common.pagination import DashboardPagination

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

    @extend_schema(responses={200: ApprovalSerializer(many=True)}, summary="List approvals")
    def get(self, request):
        outcome = request.query_params.get("outcome", Approval.Outcome.PENDING)
        if outcome != "all" and outcome not in Approval.Outcome.values:
            return Response(
                {"detail": "outcome must be pending, approved, denied, expired, or all."},
                status=status.HTTP_400_BAD_REQUEST,
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

    @extend_schema(responses={200: ApprovalSerializer}, summary="Get an approval")
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
        except services.ApprovalNotFound:
            return Response({"detail": "Approval not found."}, status=status.HTTP_404_NOT_FOUND)
        except services.ApprovalExpired:
            return Response({"detail": "This approval has expired."}, status=status.HTTP_409_CONFLICT)
        except services.ApprovalConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except services.ApprovalRecheckFailed as exc:
            return Response(
                {"detail": str(exc), "rules": exc.rules},
                status=status.HTTP_409_CONFLICT,
            )
        approval = get_object_or_404(approval_queryset(request.user), pk=approval.pk)
        return Response(ApprovalSerializer(approval).data)


class ApprovalApproveView(DecisionMixin, APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsApprover]

    @extend_schema(
        request=DecisionSerializer,
        responses={200: ApprovalSerializer},
        summary="Approve a pending request after a recheck",
    )
    def post(self, request, pk):
        return self._decide(request, pk, approve=True)


class ApprovalDenyView(DecisionMixin, APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsApprover]

    @extend_schema(
        request=DecisionSerializer,
        responses={200: ApprovalSerializer},
        summary="Deny a pending request",
    )
    def post(self, request, pk):
        return self._decide(request, pk, approve=False)
