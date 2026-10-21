import uuid

from django.db import models, transaction

from apps.accounts.models import Organization

from .keys import hash_key, key_prefix, new_raw_key


class Agent(models.Model):
    """An AI agent that submits spend requests for one organization."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="agents")
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="unique_agent_name_per_org"),
        ]

    def __str__(self) -> str:
        return self.name

    @classmethod
    @transaction.atomic
    def create_with_key(cls, name: str, organization: Organization):
        """Create an agent and its first key, returning (agent, raw_key). The raw key is not stored."""
        agent = cls.objects.create(name=name, organization=organization)
        _, raw_key = ApiKey.create_key(agent)
        return agent, raw_key


class ApiKey(models.Model):
    """A rotatable agent credential. Only a prefix and a hash of the secret are stored."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="api_keys")
    prefix = models.CharField(max_length=16, unique=True, editable=False)
    key_hash = models.CharField(max_length=64, editable=False)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.prefix} for {self.agent}"

    @classmethod
    def create_key(cls, agent: Agent):
        """Create and persist a key, returning (api_key, raw_key)."""
        raw_key = new_raw_key()
        api_key = cls.objects.create(
            agent=agent,
            prefix=key_prefix(raw_key),
            key_hash=hash_key(raw_key),
        )
        return api_key, raw_key
