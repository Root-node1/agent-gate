from django.urls import path

from . import views

urlpatterns = [
    path("approvals/", views.ApprovalListView.as_view(), name="approval-list"),
    path("approvals/<uuid:pk>/", views.ApprovalDetailView.as_view(), name="approval-detail"),
    path(
        "approvals/<uuid:pk>/approve/",
        views.ApprovalApproveView.as_view(),
        name="approval-approve",
    ),
    path(
        "approvals/<uuid:pk>/deny/",
        views.ApprovalDenyView.as_view(),
        name="approval-deny",
    ),
]
