from django.urls import path

from . import views

urlpatterns = [
    path("audit/", views.AuditListView.as_view(), name="audit-list"),
    path("audit/verify/", views.AuditVerifyView.as_view(), name="audit-verify"),
]
