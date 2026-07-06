"""Auth URLs for void API."""
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

urlpatterns = [
    path("login/", TokenObtainPairView.as_view(), name="void_token_obtain_pair"),
    path("refresh/", TokenRefreshView.as_view(), name="void_token_refresh"),
    path("me/", views.CurrentUserView.as_view(), name="void_current_user"),
    path("change-password/", views.ChangePasswordView.as_view(), name="void_change_password"),
]
