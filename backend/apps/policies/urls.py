from django.urls import path

from . import views

urlpatterns = [
    path("policies/", views.PolicyListView.as_view(), name="policy-list"),
    path("policies/<uuid:pk>/", views.PolicyDetailView.as_view(), name="policy-detail"),
    path(
        "policies/<uuid:pk>/merchant-rules/",
        views.MerchantRuleCreateView.as_view(),
        name="merchant-rule-create",
    ),
    path(
        "policies/<uuid:pk>/merchant-rules/<uuid:rule_id>/",
        views.MerchantRuleDeleteView.as_view(),
        name="merchant-rule-delete",
    ),
]
