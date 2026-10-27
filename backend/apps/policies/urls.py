from django.urls import path

from . import views

urlpatterns = [
    path("policies/", views.PolicyListView.as_view(), name="policy-list"),
    path("policies/<uuid:pk>/", views.PolicyDetailView.as_view(), name="policy-detail"),
]
