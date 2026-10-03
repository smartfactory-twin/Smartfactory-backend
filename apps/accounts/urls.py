from django.urls import path
from .views import (
    LoginView,
    LogoutView,
    CustomTokenRefreshView,
    RegisterView,
    MeView,
    PasswordResetView,
    PasswordResetConfirmView,
    AdminUserCreateView,
    AdminUserListView,
    AdminUserDeleteView,
    UpdateProfileView,
    ChangePasswordView,
)

urlpatterns = [
    path('login/',                  LoginView.as_view(),              name='auth-login'),
    path('logout/',                 LogoutView.as_view(),             name='auth-logout'),
    path('token/refresh/',          CustomTokenRefreshView.as_view(), name='token-refresh'),
    path('register/',               RegisterView.as_view(),           name='auth-register'),
    path('me/',                     MeView.as_view(),                 name='auth-me'),
    path('me/update/',              UpdateProfileView.as_view(),      name='auth-update-profile'),
    path('me/change-password/',     ChangePasswordView.as_view(),     name='auth-change-password'),
    path('password-reset/',         PasswordResetView.as_view(),      name='password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(),name='password-reset-confirm'),
    path('users/',                  AdminUserCreateView.as_view(),    name='admin-create-user'),
    path('users/list/',             AdminUserListView.as_view(),      name='admin-list-users'),
    path('users/<int:pk>/delete/',  AdminUserDeleteView.as_view(),    name='admin-delete-user'),
]
