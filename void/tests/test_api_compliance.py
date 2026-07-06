"""Tests for void compliance REST API."""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from void.models import (
    ComplianceAuthority,
    ComplianceStandard,
    Point,
    PointComplianceProfile,
    VoidUserProfile,
)

User = get_user_model()


class ComplianceAPITests(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"voidadmin_{self.suffix}",
            email=f"voidadmin_{self.suffix}@smarthydro.cl",
            password="testpass123",
        )
        VoidUserProfile.objects.create(user=self.user, role="admin")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.authority = ComplianceAuthority.objects.create(
            code=f"dga_{self.suffix}",
            name="DGA",
            protocol="HTTP_REST",
            auth_type="BEARER",
            auth_token="secret",
            base_url="https://apimee.mop.gob.cl/api/v1",
        )
        self.standard = ComplianceStandard.objects.create(
            code=f"MAYOR_{self.suffix}",
            name="Mayor",
            send_minute=0,
        )
        self.point = Point.objects.create(name=f"P-API-Compliance-{self.suffix}")

    def test_list_authorities(self):
        url = reverse("void:complianceauthority-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        codes = [a["code"] for a in response.data["results"]]
        self.assertIn(self.authority.code, codes)

    def test_create_authority(self):
        url = reverse("void:complianceauthority-list")
        response = self.client.post(url, {
            "code": f"sma_{self.suffix}",
            "name": "SMA",
            "protocol": "HTTP_REST",
            "auth_type": "NONE",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(ComplianceAuthority.objects.filter(code=f"sma_{self.suffix}").exists())

    def test_password_write_only(self):
        url = reverse("void:complianceauthority-detail", kwargs={"pk": self.authority.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("secret", str(response.data))
        self.assertEqual(response.data["code"], self.authority.code)

    def test_create_standard(self):
        url = reverse("void:compliancestandard-list")
        response = self.client.post(url, {
            "code": f"MEDIO_{self.suffix}",
            "name": "Medio",
            "send_minute": 0,
            "send_hour": 0,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(ComplianceStandard.objects.filter(code=f"MEDIO_{self.suffix}").exists())

    def test_create_profile(self):
        url = reverse("void:pointcomplianceprofile-list")
        response = self.client.post(url, {
            "point": self.point.pk,
            "authority_id": self.authority.pk,
            "standard_id": self.standard.pk,
            "external_code": "OBRA-API-1",
            "type_key": "SUBTERRANEO",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        profile = PointComplianceProfile.objects.get(pk=response.data["id"])
        self.assertEqual(profile.external_code, "OBRA-API-1")
        self.assertEqual(profile.authority.code, self.authority.code)
        self.assertEqual(profile.standard.code, self.standard.code)

    def test_profile_list_filter_by_point(self):
        PointComplianceProfile.objects.create(
            point=self.point,
            authority=self.authority,
            standard=self.standard,
        )
        url = reverse("void:pointcomplianceprofile-list")
        response = self.client.get(url, {"point": self.point.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_unauthenticated_access_denied(self):
        self.client.force_authenticate(user=None)
        url = reverse("void:complianceauthority-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)
