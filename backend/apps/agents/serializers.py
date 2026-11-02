"""Serializers for agent management endpoints."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import OrgMembership

from .models import Agent


class AgentSerializer(serializers.ModelSerializer):
    """Full detail serializer. Returns a lightweight list shape when
    ``context['list_view']`` is true."""

    organization_name = serializers.CharField(source="organization.name", read_only=True)
    current_key = serializers.SerializerMethodField()
    current_key_prefix = serializers.SerializerMethodField()
    policies = serializers.SerializerMethodField()
    recent_spend_requests = serializers.SerializerMethodField()
    today_spend_minor = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Agent
        fields = [
            "id",
            "name",
            "organization",
            "organization_name",
            "status",
            "created_at",
            "updated_at",
            "current_key",
            "current_key_prefix",
            "policies",
            "recent_spend_requests",
            "today_spend_minor",
            "currency",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self.context.get("list_view"):
            return {
                "id": data["id"],
                "name": data["name"],
                "status": data["status"],
                "created_at": data["created_at"],
                "updated_at": data["updated_at"],
                "current_key_prefix": data["current_key_prefix"],
            }
        return data

    def get_current_key(self, obj):
        key = obj.current_key
        if key is None:
            return None
        return {
            "prefix": key.prefix,
            "created_at": key.created_at,
            "last_used_at": key.last_used_at,
        }

    def get_current_key_prefix(self, obj):
        key = obj.current_key
        return key.prefix if key else None

    def get_policies(self, obj):
        return [
            {
                "id": str(p.id),
                "version": p.version,
                "name": p.name,
                "currency": p.currency,
            }
            for p in obj.policies.all()[:5]
        ]

    def get_recent_spend_requests(self, obj):
        return obj.spend_requests.count()

    def get_today_spend_minor(self, obj):
        from django.db.models import Sum
        from django.utils import timezone

        today = timezone.now().date()
        result = obj.spend_requests.filter(
            created_at__date=today
        ).aggregate(total=Sum("amount_minor"))
        return result["total"] or 0

    @extend_schema_field(serializers.CharField)
    def get_currency(self, obj):
        policy = obj.policies.first()
        return policy.currency if policy else "USD"


class AgentCreateSerializer(serializers.Serializer):
    """Input validation for agent creation. Rejects unknown fields."""

    name = serializers.CharField(max_length=100)
    organization = serializers.UUIDField()

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Unknown field." for field in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate_name(self, value):
        if value != value.strip():
            raise serializers.ValidationError("Name must not have leading or trailing whitespace.")
        return value

    def validate_organization(self, value):
        user = self.context["request"].user
        if not OrgMembership.objects.filter(
            user=user,
            organization_id=value,
            role=OrgMembership.Role.ADMIN,
        ).exists():
            raise serializers.ValidationError("You are not an administrator of this organization.")
        return value


class AgentUpdateSerializer(serializers.ModelSerializer):
    """Partial update of permitted agent fields (name, status)."""

    class Meta:
        model = Agent
        fields = ["name", "status"]

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Unknown field." for field in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate_name(self, value):
        if value != value.strip():
            raise serializers.ValidationError("Name must not have leading or trailing whitespace.")
        return value

    def validate_status(self, value):
        if value in (Agent.Status.ACTIVE, Agent.Status.SUSPENDED):
            return value
        raise serializers.ValidationError("Status must be 'active' or 'suspended'.")

    def validate(self, attrs):
        if "name" in attrs:
            org_id = self.instance.organization_id
            if (
                Agent.objects.filter(organization_id=org_id, name=attrs["name"])
                .exclude(pk=self.instance.pk)
                .exists()
            ):
                raise serializers.ValidationError(
                    {"name": "Another agent in this organization already has this name."}
                )
        return attrs
