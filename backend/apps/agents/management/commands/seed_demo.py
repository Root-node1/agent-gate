"""Create a fresh demo agent without deleting the previous one or its audit trail."""

from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Organization, OrgMembership, User
from apps.audit.models import AuditEvent
from apps.policies.models import Policy

from ...models import Agent

DEMO_PREFIX = "demo-"


class Command(BaseCommand):
    help = "Create a fresh demo agent and policy, suspending the previous demo agent."

    def _demo_user(self, organization):
        """Create or reuse the passwordless principal used by anonymous demo mode."""
        username = settings.DEMO_USERNAME
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": ""},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        elif user.has_usable_password() or user.is_staff or user.is_superuser:
            raise CommandError(
                f"{username!r} is a real account; choose another DEMO_USERNAME."
            )
        if user.memberships.exclude(organization=organization).exists():
            raise CommandError(
                f"{username!r} belongs to another organization; choose another DEMO_USERNAME."
            )
        OrgMembership.objects.update_or_create(
            user=user,
            organization=organization,
            defaults={"role": OrgMembership.Role.APPROVER},
        )
        return user

    @transaction.atomic
    def handle(self, *args, **options):
        organization, _ = Organization.objects.get_or_create(name=settings.DEMO_ORG_NAME)
        demo_user = self._demo_user(organization)
        previous = (
            Agent.objects.filter(organization=organization, name__startswith=DEMO_PREFIX)
            .exclude(status=Agent.Status.SUSPENDED)
            .order_by("-created_at")
            .first()
        )
        if previous is not None:
            Agent.objects.filter(pk=previous.pk).update(status=Agent.Status.SUSPENDED)

        agent, raw_key = Agent.create_with_key(f"{DEMO_PREFIX}{uuid4().hex[:8]}", organization)
        Policy.objects.create(agent=agent)
        AuditEvent.record(
            AuditEvent.EventType.DEMO_RESET,
            organization=organization,
            agent=agent,
            actor_type=AuditEvent.ActorType.SYSTEM,
            previous_agent_id=str(previous.pk) if previous else None,
            agent_name=agent.name,
            demo_user_id=str(demo_user.pk),
        )
        self.stdout.write(f"Demo agent: {agent.name}")
        self.stdout.write(f"API key: {raw_key}")
        self.stdout.write(f"Demo dashboard user: {demo_user.username}")
