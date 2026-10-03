from django.urls import path
from .views import (
    LoginView,
    LogoutView,
    CustomTokenRefreshView,
    RegisterView,
    MeView,
    PasswordResetView,
    PasswordResetConfirmView,
)

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token-refresh'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('password-reset/', PasswordResetView.as_view(), name='password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]
