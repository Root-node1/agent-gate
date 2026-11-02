from django.urls import path

from .views import CurrentUserView, LogoutView

urlpatterns = [
    path("user/", CurrentUserView.as_view(), name="auth-user"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
]
