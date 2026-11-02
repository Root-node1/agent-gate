import uuid

from django.db import models, transaction
from django.utils import timezone

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

    @property
    def current_key(self):
        """The most recent non-revoked key, or None."""
        return self.api_keys.filter(revoked_at__isnull=True).first()

    @transaction.atomic
    def rotate_key(self):
        """Revoke the current non-revoked key and create a new one.

        Returns (new_api_key, raw_key). The raw key is returned only to the caller.
        """
        current = self.current_key
        if current is not None:
            current.revoke()
        return ApiKey.create_key(self)

    @transaction.atomic
    def revoke_current_key(self):
        """Revoke the current non-revoked key. Returns the revoked key or None."""
        current = self.current_key
        if current is None:
            return None
        current.revoke()
        return current


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

    def revoke(self):
        """Soft-delete this key by setting revoked_at. Never purges from the database."""
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at", "updated_at"])

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
