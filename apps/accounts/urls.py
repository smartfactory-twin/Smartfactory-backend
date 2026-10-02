from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    LoginView,
    LogoutView,
    RegisterView,
    MeView,
    ChangePasswordView,
    UserListView,
)

urlpatterns = [
    # Auth
    path('login/',           LoginView.as_view(),          name='auth-login'),
    path('logout/',          LogoutView.as_view(),          name='auth-logout'),
    path('token/refresh/',   TokenRefreshView.as_view(),    name='token-refresh'),
    path('register/',        RegisterView.as_view(),        name='auth-register'),

    # Profil
    path('me/',              MeView.as_view(),              name='auth-me'),
    path('change-password/', ChangePasswordView.as_view(),  name='auth-change-password'),

    # Admin
    path('users/',           UserListView.as_view(),        name='user-list'),
]
