from django.urls import path

from .checkout.views import CheckoutOrderCaptureView, CheckoutOrderCreateView

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
]
