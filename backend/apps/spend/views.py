from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import SpendRequest
from .serializers import SpendRequestCreateSerializer, SpendRequestSerializer


class SpendRequestCreateView(APIView):
    @extend_schema(
        request=SpendRequestCreateSerializer,
        responses={201: SpendRequestSerializer},
        summary="Submit a spend request",
        description=(
            "Returns 201 with the firewall's decision in the body: allow, deny or needs_approval. "
            "Always read `decision`; the status code alone does not mean the payment is allowed."
        ),
    )
    def post(self, request):
        serializer = SpendRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            spend_request = services.submit_spend_request(
                request.user.agent, **serializer.validated_data
            )
        except services.PolicyMissing:
            return Response(
                {"detail": "This agent has no policy configured."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(SpendRequestSerializer(spend_request).data, status=status.HTTP_201_CREATED)


class SpendRequestDetailView(APIView):
    @extend_schema(responses={200: SpendRequestSerializer}, summary="Get a spend request")
    def get(self, request, pk):
        spend_request = get_object_or_404(
            SpendRequest.objects.select_related("approval"),
            pk=pk,
            agent=request.user.agent,
        )
        return Response(SpendRequestSerializer(spend_request).data)
