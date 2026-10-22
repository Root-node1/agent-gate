from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Organization
from apps.audit.models import AuditEvent
from apps.common.currency import normalize_currency
from apps.common.money import to_minor
from apps.policies.models import MerchantRule, Policy
from engine import normalize_merchant

from ...models import Agent


class Command(BaseCommand):
    help = "Create an agent with a policy and print its API key once."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument("--org", default="default", help="Organization name")
        parser.add_argument("--currency", default="USD")
        parser.add_argument("--cap", default="100.00", help="Per-transaction cap")
        parser.add_argument("--threshold", default="50.00", help="Amount above which a human must approve")
        parser.add_argument("--daily", default="500.00", help="Daily budget")
        parser.add_argument("--monthly", default="5000.00", help="Monthly budget")
        parser.add_argument("--allow", action="append", default=[], help="Allowed merchant (repeatable)")
        parser.add_argument("--block", action="append", default=[], help="Blocked merchant (repeatable)")

    @transaction.atomic
    def handle(self, *args, **options):
        organization, _ = Organization.objects.get_or_create(name=options["org"])
        name = options["name"]
        if Agent.objects.filter(organization=organization, name=name).exists():
            raise CommandError(f"Agent '{name}' already exists.")

        try:
            currency = normalize_currency(options["currency"])
        except ValidationError as exc:
            raise CommandError(exc.messages[0]) from None

        try:
            cap = Decimal(options["cap"])
            threshold = Decimal(options["threshold"])
            daily = Decimal(options["daily"])
            monthly = Decimal(options["monthly"])
        except InvalidOperation:
            raise CommandError("--cap, --threshold, --daily and --monthly must be numbers.") from None
        for label, value in (("--cap", cap), ("--threshold", threshold), ("--daily", daily), ("--monthly", monthly)):
            if value < 0:
                raise CommandError(f"{label} must not be negative.")
        if threshold > cap:
            raise CommandError("--threshold cannot exceed --cap.")

        allowed = {normalize_merchant(m) for m in options["allow"]}
        blocked = {normalize_merchant(m) for m in options["block"]}
        overlap = allowed & blocked
        if overlap:
            raise CommandError(f"Merchants cannot be both allowed and blocked: {', '.join(sorted(overlap))}")

        agent, raw_key = Agent.create_with_key(name, organization)
        policy = Policy.objects.create(
            organization=organization,
            agent=agent,
            currency=currency,
            per_transaction_cap_minor=to_minor(cap, currency),
            approval_threshold_minor=to_minor(threshold, currency),
            daily_budget_minor=to_minor(daily, currency),
            monthly_budget_minor=to_minor(monthly, currency),
        )
        for merchant in sorted(allowed):
            MerchantRule.objects.create(
                policy=policy, merchant_ref=merchant, kind=MerchantRule.Kind.ALLOW
            )
        for merchant in sorted(blocked):
            MerchantRule.objects.create(
                policy=policy, merchant_ref=merchant, kind=MerchantRule.Kind.BLOCK
            )

        AuditEvent.record(
            AuditEvent.EventType.AGENT_CREATED,
            organization=organization,
            agent=agent,
            actor_type=AuditEvent.ActorType.SYSTEM,
            name=name,
        )
        AuditEvent.record(
            AuditEvent.EventType.KEY_CREATED,
            organization=organization,
            agent=agent,
            actor_type=AuditEvent.ActorType.SYSTEM,
            prefix=agent.api_keys.get().prefix,
        )

        self.stdout.write(self.style.SUCCESS(f"Created agent '{name}'."))
        self.stdout.write(f"API key (shown once, store it safely): {raw_key}")
