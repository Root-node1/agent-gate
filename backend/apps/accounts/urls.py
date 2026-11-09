from django.urls import path

from .views import CurrentUserView, LogoutView, ProfileView

urlpatterns = [
    path("user/", CurrentUserView.as_view(), name="auth-user"),
    path("profile/", ProfileView.as_view(), name="auth-profile"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
]
