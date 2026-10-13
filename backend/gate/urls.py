from django.urls import path

from . import views

urlpatterns = [
    path("spend-requests/", views.SpendRequestCreateView.as_view(), name="spend-request-create"),
    path("spend-requests/<uuid:pk>/", views.SpendRequestDetailView.as_view(), name="spend-request-detail"),
]
