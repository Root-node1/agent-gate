from allauth.account.models import EmailAddress
from rest_framework import serializers

from .models import AccountProfile, OrgMembership, User


class MembershipSerializer(serializers.ModelSerializer):
    organization = serializers.CharField(source="organization.name")

    class Meta:
        model = OrgMembership
        fields = ["organization", "role"]


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

    def get_is_email_verified(self, user) -> bool:
        if not user.email:
            return False
        return EmailAddress.objects.filter(
            user=user, email=user.email, verified=True
        ).exists()
