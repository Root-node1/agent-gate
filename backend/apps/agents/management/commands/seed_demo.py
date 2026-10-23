"""Create a fresh demo agent without deleting the previous one or its audit trail."""

from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Organization
from apps.audit.models import AuditEvent
from apps.policies.models import Policy

from ...models import Agent

DEMO_PREFIX = "demo-"


class Command(BaseCommand):
    help = "Create a fresh demo agent and policy, suspending the previous demo agent."

    @transaction.atomic
    def handle(self, *args, **options):
        organization, _ = Organization.objects.get_or_create(name=settings.DEMO_ORG_NAME)
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
        )
        self.stdout.write(f"Demo agent: {agent.name}")
        self.stdout.write(f"API key: {raw_key}")
