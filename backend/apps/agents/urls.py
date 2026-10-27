from django.urls import path

from . import views

urlpatterns = [
    path("agents/", views.AgentListView.as_view(), name="agent-list"),
    path("agents/<uuid:pk>/", views.AgentDetailView.as_view(), name="agent-detail"),
    path("agents/<uuid:pk>/rotate-key/", views.AgentRotateKeyView.as_view(), name="agent-rotate-key"),
    path("agents/<uuid:pk>/revoke-key/", views.AgentRevokeKeyView.as_view(), name="agent-revoke-key"),
]
