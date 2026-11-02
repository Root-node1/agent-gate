from allauth.account.models import EmailAddress
from rest_framework import serializers

from .models import OrgMembership, User


class MembershipSerializer(serializers.ModelSerializer):
    organization = serializers.CharField(source="organization.name")

    class Meta:
        model = OrgMembership
        fields = ["organization", "role"]


class CurrentUserSerializer(serializers.ModelSerializer):
    is_email_verified = serializers.SerializerMethodField()
    memberships = MembershipSerializer(many=True, read_only=True)

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
        ]

    def get_is_email_verified(self, user):
        if not user.email:
            return False
        return EmailAddress.objects.filter(
            user=user, email=user.email, verified=True
        ).exists()
