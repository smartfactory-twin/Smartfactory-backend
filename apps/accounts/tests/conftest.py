import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def regular_user(db):
    user_model = get_user_model()
    return user_model.objects.create_user(
        email='google-user@example.com',
        password='User@123456',
        nom='Google',
        prenom='Test',
        role=user_model.Role.OPERATEUR,
    )
