"""Durable payout reservation domain (INT-13I).

A PayoutReservation is a durable, idempotent record that an approved
SpendRequest has been authorized for payout.  Reservation does NOT transfer
money; it only locks the right to submit a PayPal Payout later.
"""

import uuid

from django.db import models
from django.db.models import Q

from apps.accounts.models import Organization
from apps.common.currency import normalize_currency, validate_currency

from ..models import CheckoutOrder  # noqa: F401  (keeps app model imports grouped)


class PayoutReservation(models.Model):
    """One durable payout reservation for an approved SpendRequest.

    Lifecycle (forward-only):

        RESERVED  (terminal for INT-13I; submission happens later)

    Financial and recipient fields are immutable snapshots taken at
    reservation time, so the reservation can never be retargeted to a
    different amount, currency, or payee.

    Operation identity (idempotency)
    ----------------------------------
    Every ``PayoutReservation`` has a stable primary key (``id``) that never
    changes.  A caller-supplied ``idempotency_key`` gives later services a
    durable handle for duplicate detection without relying on PayPal's
    idempotency window:

    * ``idempotency_key`` — one per reservation attempt, unique when set.

    Reserving an operation atomically before any external call:

    * **Reservation**: insert a ``PayoutReservation`` row with the caller-supplied
      ``idempotency_key`` inside a transaction.  The ``UNIQUE`` constraint turns
      a concurrent duplicate into an ``IntegrityError``; the caller then reads
      the existing row by ``idempotency_key`` and returns its current state.

    The key is never regenerated on retry: the caller supplies a stable UUID
    and retries with the same value, so the operation resolves to the same row.
    """

    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        SUBMISSION_PENDING = "submission_pending", "Submission pending"
        SUBMITTED = "submitted", "Submitted to PayPal"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        UNCERTAIN = "uncertain", "Outcome uncertain"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="payout_reservations"
    )
    spend_request = models.OneToOneField(
        "spend.SpendRequest",
        on_delete=models.PROTECT,
        related_name="payout_reservation",
    )
    payee = models.ForeignKey(
        "payees.Payee",
        on_delete=models.PROTECT,
        related_name="payout_reservations",
    )

    # Immutable financial snapshot.
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(
        max_length=3, default="USD", validators=[validate_currency]
    )

    # Immutable recipient snapshot.
    destination_type = models.CharField(max_length=20)
    destination_value = models.CharField(max_length=500)
    destination_fingerprint = models.CharField(max_length=64)

    idempotency_key = models.UUIDField(null=True, blank=True, editable=False)

    # Stable PayPal sender batch ID, generated once at submission and reused
    # across retries so PayPal dedupes duplicate batches.
    sender_batch_id = models.UUIDField(null=True, blank=True, editable=False)

    # Nullable future PayPal Payouts identifiers (set after submission).
    paypal_payout_batch_id = models.CharField(max_length=100, null=True, blank=True)
    paypal_payout_item_id = models.CharField(max_length=100, null=True, blank=True)

    submission_attempted_at = models.DateTimeField(null=True, blank=True)
    submission_error = models.TextField(null=True, blank=True)

    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.RESERVED
    )

    reconciliation_metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "created_at"], name="payout_org_created_idx"
            ),
            models.Index(fields=["status"], name="payout_status_idx"),
            models.Index(
                fields=["organization", "status"], name="payout_org_status_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_minor__gt=0), name="payout_amount_positive"
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_payout_idempotency_key",
            ),
            models.UniqueConstraint(
                fields=["paypal_payout_batch_id"],
                condition=Q(paypal_payout_batch_id__isnull=False),
                name="unique_paypal_payout_batch_id",
            ),
            models.UniqueConstraint(
                fields=["paypal_payout_item_id"],
                condition=Q(paypal_payout_item_id__isnull=False),
                name="unique_paypal_payout_item_id",
            ),
            models.UniqueConstraint(
                fields=["sender_batch_id"],
                condition=Q(sender_batch_id__isnull=False),
                name="unique_payout_sender_batch_id",
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
        instance._original_spend_request_id = instance.spend_request_id
        instance._original_payee_id = instance.payee_id
        instance._original_destination_type = instance.destination_type
        instance._original_destination_value = instance.destination_value
        instance._original_destination_fingerprint = instance.destination_fingerprint
        instance._original_sender_batch_id = instance.sender_batch_id
        return instance

    def save(self, *args, **kwargs):
        self.currency = normalize_currency(self.currency)

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
            if (
                getattr(self, "_original_spend_request_id", None) is not None
                and self.spend_request_id != self._original_spend_request_id
            ):
                raise ValueError("spend_request is immutable after creation.")
            if (
                getattr(self, "_original_payee_id", None) is not None
                and self.payee_id != self._original_payee_id
            ):
                raise ValueError("payee is immutable after creation.")
            if (
                getattr(self, "_original_destination_type", None) is not None
                and self.destination_type != self._original_destination_type
            ):
                raise ValueError("destination_type is immutable after creation.")
            if (
                getattr(self, "_original_destination_value", None) is not None
                and self.destination_value != self._original_destination_value
            ):
                raise ValueError("destination_value is immutable after creation.")
            if (
                getattr(self, "_original_destination_fingerprint", None) is not None
                and self.destination_fingerprint
                != self._original_destination_fingerprint
            ):
                raise ValueError("destination_fingerprint is immutable after creation.")
            if (
                getattr(self, "_original_sender_batch_id", None) is not None
                and self.sender_batch_id != self._original_sender_batch_id
            ):
                raise ValueError("sender_batch_id is immutable after creation.")

        super().save(*args, **kwargs)
        self._original_status = self.status
        self._original_amount_minor = self.amount_minor
        self._original_currency = self.currency
        self._original_organization_id = self.organization_id
        self._original_spend_request_id = self.spend_request_id
        self._original_payee_id = self.payee_id
        self._original_destination_type = self.destination_type
        self._original_destination_value = self.destination_value
        self._original_destination_fingerprint = self.destination_fingerprint
        self._original_sender_batch_id = self.sender_batch_id
