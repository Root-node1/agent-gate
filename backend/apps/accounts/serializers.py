from allauth.account.models import EmailAddress
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import AccountProfile, OrgMembership, User


class MembershipSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)
    organization = serializers.CharField(source="organization.name")

    class Meta:
        model = OrgMembership
        fields = ["organization_id", "organization", "role"]


class OrganizationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=200)


class OrganizationCreateResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=OrgMembership.Role.choices)


class AccountProfileSerializer(serializers.ModelSerializer):
    """Profile display information. Organization membership is read-only
    and managed through Organization + OrgMembership, never through this
    serializer."""

    class Meta:
        model = AccountProfile
        fields = ["full_name"]
        read_only_fields = ["user"]


class SessionRememberSerializer(serializers.Serializer):
    remember = serializers.BooleanField(required=True)


class CurrentUserSerializer(serializers.ModelSerializer):
    is_email_verified = serializers.SerializerMethodField()
    memberships = MembershipSerializer(many=True, read_only=True)
    profile = AccountProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "date_joined",
            "is_email_verified",
            "memberships",
            "profile",
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_is_email_verified(self, user) -> bool:
        if not user.email:
            return False
        return EmailAddress.objects.filter(
            user=user, email=user.email, verified=True
        ).exists()
