"""URLs for durable payout reservation (INT-13I)."""

from django.urls import path

from .views import PayoutReservationCreateView

urlpatterns = [
    path(
        "",
        PayoutReservationCreateView.as_view(),
        name="payout-reservation-create",
    ),
]
