from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from gate.models import Agent, MerchantRule, Policy
from gate.rules import normalize_merchant


class Command(BaseCommand):
    help = "Create an agent with a policy and print its API key once."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument("--currency", default="USD")
        parser.add_argument("--cap", default="100.00", help="Per-transaction cap")
        parser.add_argument("--threshold", default="50.00", help="Amount above which a human must approve")
        parser.add_argument("--daily", default="500.00", help="Daily budget")
        parser.add_argument("--monthly", default="5000.00", help="Monthly budget")
        parser.add_argument("--allow", action="append", default=[], help="Allowed merchant (repeatable)")
        parser.add_argument("--block", action="append", default=[], help="Blocked merchant (repeatable)")

    @transaction.atomic
    def handle(self, *args, **options):
        name = options["name"]
        if Agent.objects.filter(name=name).exists():
            raise CommandError(f"Agent '{name}' already exists.")

        try:
            cap = Decimal(options["cap"])
            threshold = Decimal(options["threshold"])
            daily = Decimal(options["daily"])
            monthly = Decimal(options["monthly"])
        except InvalidOperation:
            raise CommandError("--cap, --threshold, --daily and --monthly must be numbers.") from None
        if threshold > cap:
            raise CommandError("--threshold cannot exceed --cap.")

        allowed = {normalize_merchant(m) for m in options["allow"]}
        blocked = {normalize_merchant(m) for m in options["block"]}
        overlap = allowed & blocked
        if overlap:
            raise CommandError(f"Merchants cannot be both allowed and blocked: {', '.join(sorted(overlap))}")

        agent, raw_key = Agent.create_with_key(name)
        policy = Policy.objects.create(
            agent=agent,
            currency=options["currency"].upper(),
            per_transaction_cap=cap,
            approval_threshold=threshold,
            daily_budget=daily,
            monthly_budget=monthly,
        )
        for merchant in sorted(allowed):
            MerchantRule.objects.create(policy=policy, merchant=merchant, action=MerchantRule.Action.ALLOW)
        for merchant in sorted(blocked):
            MerchantRule.objects.create(policy=policy, merchant=merchant, action=MerchantRule.Action.BLOCK)

        self.stdout.write(self.style.SUCCESS(f"Created agent '{name}'."))
        self.stdout.write(f"API key (shown once, store it safely): {raw_key}")
