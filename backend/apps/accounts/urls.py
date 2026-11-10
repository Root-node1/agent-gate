from django.urls import path

from .views import (
    AuthOptionsView,
    CsrfTokenView,
    CurrentUserView,
    LogoutView,
    ProfileView,
    SessionRememberView,
    SessionStatusView,
)

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("options/", AuthOptionsView.as_view(), name="auth-options"),
    path("session/", SessionStatusView.as_view(), name="auth-session"),
    path("session/remember/", SessionRememberView.as_view(), name="auth-remember"),
    path("user/", CurrentUserView.as_view(), name="auth-user"),
    path("profile/", ProfileView.as_view(), name="auth-profile"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
]
