"""Tests for void Point API."""
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from void.models import (
    Client,
    Device,
    Point,
    PointGroup,
    PointPermission,
    ProcessedReading,
    Project,
    Provider,
    VoidUserProfile,
)

User = get_user_model()


class PointAPITests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="adminuser",
            email="admin@smarthydro.cl",
            password="testpass123",
        )
        self.admin_profile = VoidUserProfile.objects.create(
            user=self.admin_user,
            role="admin",
        )

        self.client_user = User.objects.create_user(
            username="clientuser",
            email="client@smarthydro.cl",
            password="testpass123",
        )
        self.client_profile = VoidUserProfile.objects.create(
            user=self.client_user,
            role="client_admin",
        )

        self.client_obj = Client.objects.create(name="Test Client")
        self.project = Project.objects.create(
            name="Test Project",
            client=self.client_obj,
        )

        self.point = Point.objects.create(
            name="P-Test",
            code_internal="P001",
            client_fk=self.client_obj,
            project_fk=self.project,
            frequency_minutes=15,
        )
        self.device = Device.objects.create(
            point=self.point,
            serial_number="SN001",
            configuration={"variables": ["pulses"]},
        )

        self.group = PointGroup.objects.create(name="Grupo A")
        self.group.points.add(self.point)
        PointPermission.objects.create(
            user=self.client_profile,
            group=self.group,
            permission="view",
        )

        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin_user)

        self.client_client = APIClient()
        self.client_client.force_authenticate(user=self.client_user)

    def test_list_points_as_admin(self):
        url = reverse("void:point-list")
        response = self.admin_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_list_points_as_client_admin_sees_allowed(self):
        url = reverse("void:point-list")
        response = self.client_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_create_point_as_admin(self):
        url = reverse("void:point-list")
        response = self.admin_client.post(url, {
            "name": "P-New",
            "code_internal": "P002",
            "client_fk": self.client_obj.id,
            "project_fk": self.project.id,
            "frequency_minutes": 60,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Point.objects.filter(code_internal="P002").count(), 1)

    def test_point_summary(self):
        url = reverse("void:point-summary", kwargs={"pk": self.point.id})
        response = self.admin_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.point.id)
        self.assertEqual(response.data["device"]["serial_number"], "SN001")

    def test_point_config(self):
        url = reverse("void:point-config", kwargs={"pk": self.point.id})
        response = self.admin_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["frequency_minutes"], 15)

    def test_point_records_filtered(self):
        ts = timezone.make_aware(datetime(2026, 1, 1, 12, 0, 0))
        ProcessedReading.objects.create(
            device=self.device,
            variable="total",
            timestamp=ts,
            total=Decimal("100.000"),
        )
        ProcessedReading.objects.create(
            device=self.device,
            variable="flow",
            timestamp=ts,
            flow=Decimal("10.000"),
        )

        url = reverse("void:point-records", kwargs={"pk": self.point.id})
        response = self.admin_client.get(url, {"variable": "total"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["variable"], "total")

    def test_point_records_time_range(self):
        ts1 = timezone.make_aware(datetime(2026, 1, 1, 10, 0, 0))
        ts2 = timezone.make_aware(datetime(2026, 1, 1, 12, 0, 0))
        ProcessedReading.objects.create(
            device=self.device,
            variable="total",
            timestamp=ts1,
            total=Decimal("100.000"),
        )
        ProcessedReading.objects.create(
            device=self.device,
            variable="total",
            timestamp=ts2,
            total=Decimal("200.000"),
        )

        url = reverse("void:point-records", kwargs={"pk": self.point.id})
        response = self.admin_client.get(url, {
            "since": "2026-01-01T14:00:00Z",
            "until": "2026-01-01T16:00:00Z",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["total"], "200.000")
