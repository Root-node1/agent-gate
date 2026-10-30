from django.urls import path

from .checkout.views import CheckoutOrderCreateView

urlpatterns = [
    path(
        "checkout-orders/",
        CheckoutOrderCreateView.as_view(),
        name="checkout-order-create",
    ),
]
