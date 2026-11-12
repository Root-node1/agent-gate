from django.urls import include, path

from .checkout.views import CheckoutOrderCaptureView, CheckoutOrderCreateView
from .payouts.urls import urlpatterns as payouts_urlpatterns
from .webhook_views import PayPalWebhookView

urlpatterns = [
    path(
        "checkout-orders/",
        CheckoutOrderCreateView.as_view(),
        name="checkout-order-create",
    ),
    path(
        "checkout-orders/<uuid:pk>/capture/",
        CheckoutOrderCaptureView.as_view(),
        name="checkout-order-capture",
    ),
    path("payout-reservations/", include(payouts_urlpatterns)),
    path("webhooks/paypal/", PayPalWebhookView.as_view(), name="paypal-webhook"),
]
