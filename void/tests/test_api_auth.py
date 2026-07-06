"""Tests for void API authentication."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from void.models import VoidUserProfile

User = get_user_model()


class VoidAuthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="voiduser",
            email="void@smarthydro.cl",
            password="testpass123",
        )
        self.profile = VoidUserProfile.objects.create(
            user=self.user,
            role="admin",
        )
        self.client = APIClient()

    def test_login_returns_tokens(self):
        url = reverse("void:void_token_obtain_pair")
        response = self.client.post(url, {
            "email": "void@smarthydro.cl",
            "password": "testpass123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_me_requires_auth(self):
        url = reverse("void:void_current_user")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_me_returns_profile(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("void:void_current_user")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "admin")
        self.assertEqual(response.data["accessible_point_ids"], None)

    def test_change_password(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("void:void_change_password")
        response = self.client.post(url, {
            "old_password": "testpass123",
            "new_password": "newpass123456",
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpass123456"))
