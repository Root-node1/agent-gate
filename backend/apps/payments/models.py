import uuid

from django.db import models
from django.db.models import Q

from apps.accounts.models import Organization
from apps.common.currency import normalize_currency, validate_currency


class WebhookEvent(models.Model):
    """Inbox for PayPal events. The unique event id deduplicates provider retries."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paypal_event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    signature_verified = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.paypal_event_id})"


class CheckoutOrder(models.Model):
    """Organization-scoped PayPal checkout order representing incoming money.

    Lifecycle / state machine (forward-only, no arbitrary backward transitions):

        CREATED -> PAYER_ACTION_REQUIRED -> APPROVED -> CAPTURE_PENDING -> COMPLETED
                |              |                |            |
                +---> DECLINED <---------------+----> VOIDED
                +---> VOIDED

    Payer approval (``APPROVED``) is **not** captured funds.  Funds are only
    considered settled once the status reaches ``COMPLETED``.

    .. note::
        The ``save`` override guards against direct ``.save()`` calls and model
        ``.full_clean()``, but it does **not** protect against
        ``QuerySet.update()`` or raw SQL.  Services that mutate status must go
        through :meth:`transition_to`.

    Operation identity (idempotency)
    --------------------------------
    Every ``CheckoutOrder`` has a stable primary key (``id``) that never changes.
    Two caller-provided idempotency keys give later services a durable handle for
    duplicate detection and timeout reconciliation **without** relying on
    PayPal's idempotency window:

    * ``idempotency_key`` — one per create-order attempt, unique when set.
    * ``capture_idempotency_key`` — one per capture attempt, unique when set.

    Reserving an operation atomically before an external call:

    * **Create-order**: insert a ``CheckoutOrder`` row with the caller-supplied
      ``idempotency_key`` inside a transaction.  The ``UNIQUE`` constraint turns
      a concurrent duplicate into an ``IntegrityError``; the caller then reads
      the existing row by ``idempotency_key`` and returns its current state.
    * **Capture**: update ``capture_idempotency_key`` with
      ``WHERE id = :pk AND capture_idempotency_key IS NULL``.  If zero rows are
      affected or the ``UNIQUE`` constraint fires, another process owns the
      capture — look up by ``capture_idempotency_key`` and return its state.

    Neither key is regenerated on retry: the caller supplies a stable UUID and
    retries with the same value, so the operation resolves to the same row.
    """

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PAYER_ACTION_REQUIRED = "payer_action_required", "Payer action required"
        APPROVED = "approved", "Approved"
        CAPTURE_PENDING = "capture_pending", "Capture pending"
        COMPLETED = "completed", "Completed"
        DECLINED = "declined", "Declined"
        VOIDED = "voided", "Voided"

    #: Forward-only state machine: ``current -> set of allowed next statuses``.
    STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
        Status.CREATED: frozenset(
            {Status.PAYER_ACTION_REQUIRED, Status.DECLINED, Status.VOIDED}
        ),
        Status.PAYER_ACTION_REQUIRED: frozenset(
            {Status.APPROVED, Status.DECLINED, Status.VOIDED}
        ),
        Status.APPROVED: frozenset(
            {Status.CAPTURE_PENDING, Status.DECLINED, Status.VOIDED}
        ),
        Status.CAPTURE_PENDING: frozenset({Status.COMPLETED, Status.DECLINED}),
        Status.COMPLETED: frozenset(),
        Status.DECLINED: frozenset(),
        Status.VOIDED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="checkout_orders"
    )
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(
        max_length=3, default="USD", validators=[validate_currency]
    )

    idempotency_key = models.UUIDField(null=True, blank=True, editable=False)
    capture_idempotency_key = models.UUIDField(null=True, blank=True, editable=False)

    paypal_order_id = models.CharField(max_length=100, null=True, blank=True)
    paypal_capture_id = models.CharField(max_length=100, null=True, blank=True)

    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.CREATED
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "created_at"], name="checkout_org_created_idx"
            ),
            models.Index(fields=["status"], name="checkout_status_idx"),
            models.Index(
                fields=["organization", "status"], name="checkout_org_status_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_minor__gt=0), name="checkout_amount_positive"
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_checkout_idempotency_key",
            ),
            models.UniqueConstraint(
                fields=["capture_idempotency_key"],
                condition=Q(capture_idempotency_key__isnull=False),
                name="unique_checkout_capture_idempotency_key",
            ),
            models.UniqueConstraint(
                fields=["paypal_order_id"],
                condition=Q(paypal_order_id__isnull=False),
                name="unique_paypal_order_id",
            ),
            models.UniqueConstraint(
                fields=["paypal_capture_id"],
                condition=Q(paypal_capture_id__isnull=False),
                name="unique_paypal_capture_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount_minor} {self.currency} ({self.status}) [{self.id}]"

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._original_status = instance.status
        instance._original_amount_minor = instance.amount_minor
        instance._original_currency = instance.currency
        instance._original_organization_id = instance.organization_id
        return instance

    def save(self, *args, **kwargs):
        self.currency = normalize_currency(self.currency)

        original_status = getattr(self, "_original_status", None)
        if (
            not self._state.adding
            and original_status is not None
            and original_status != self.status
        ):
            allowed = self.STATUS_TRANSITIONS.get(original_status, frozenset())
            if self.status not in allowed:
                raise ValueError(
                    f"Invalid status transition from {original_status!r} to "
                    f"{self.status!r} for CheckoutOrder {self.pk}."
                )

        if not self._state.adding:
            if (
                getattr(self, "_original_amount_minor", None) is not None
                and self.amount_minor != self._original_amount_minor
            ):
                raise ValueError("amount_minor is immutable after creation.")
            if (
                getattr(self, "_original_currency", None) is not None
                and self.currency != self._original_currency
            ):
                raise ValueError("currency is immutable after creation.")
            if (
                getattr(self, "_original_organization_id", None) is not None
                and self.organization_id != self._original_organization_id
            ):
                raise ValueError("organization is immutable after creation.")

        super().save(*args, **kwargs)
        self._original_status = self.status
        self._original_amount_minor = self.amount_minor
        self._original_currency = self.currency
        self._original_organization_id = self.organization_id

    def transition_to(self, new_status: str) -> None:
        """Move to *new_status* after validating the forward-only state machine.

        Raises ``ValueError`` if the transition is not permitted from the
        current status.
        """
        allowed = self.STATUS_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid status transition from {self.status!r} to {new_status!r}."
            )
        self.status = new_status
        self.save(update_fields=["status"])
