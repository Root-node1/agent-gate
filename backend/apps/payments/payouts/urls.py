"""URLs for durable payout reservation and submission (INT-13I / INT-13J)."""

from django.urls import path

from .views import (
    PayoutReservationCreateView,
    PayoutReservationReconcileView,
    PayoutReservationSubmitView,
)

urlpatterns = [
    path(
        "",
        PayoutReservationCreateView.as_view(),
        name="payout-reservation-create",
    ),
    path(
        "<uuid:pk>/submit/",
        PayoutReservationSubmitView.as_view(),
        name="payout-reservation-submit",
    ),
    path(
        "<uuid:pk>/reconcile/",
        PayoutReservationReconcileView.as_view(),
        name="payout-reservation-reconcile",
    ),
]
