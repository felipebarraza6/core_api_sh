"""Tests for void alerts REST API."""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from void.models import (
    AlertRule,
    AlertTrigger,
    Device,
    DeviceEvent,
    Point,
    VoidUserProfile,
)

User = get_user_model()


class AlertsAPITests(TestCase):
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

        self.rule = AlertRule.objects.create(
            name=f"API rule {self.suffix}",
            event_types=["counter_reset"],
            channels=["in_app"],
        )
        self.point = Point.objects.create(name=f"P-API-Alert-{self.suffix}")
        self.device = Device.objects.create(point=self.point, configuration={})
        self.event = DeviceEvent.objects.create(
            device=self.device,
            variable="pulses",
            event_type="counter_reset",
            severity="warning",
            timestamp=timezone.now(),
            is_dispatched=True,
        )
        self.trigger = AlertTrigger.objects.create(
            rule=self.rule,
            event=self.event,
            channels=["in_app"],
            message="Test",
        )

    def test_list_rules(self):
        url = reverse("void:alertrule-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        names = [r["name"] for r in response.data["results"]]
        self.assertIn(self.rule.name, names)

    def test_create_rule(self):
        url = reverse("void:alertrule-list")
        response = self.client.post(url, {
            "name": f"New rule {self.suffix}",
            "event_types": ["device_offline"],
            "severities": ["critical"],
            "channels": ["email", "in_app"],
            "recipients": {"emails": ["a@x.com"]},
            "cooldown_minutes": 30,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AlertRule.objects.filter(name=f"New rule {self.suffix}").exists())

    def test_update_rule(self):
        url = reverse("void:alertrule-detail", kwargs={"pk": self.rule.pk})
        response = self.client.patch(url, {
            "cooldown_minutes": 120,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.cooldown_minutes, 120)

    def test_list_triggers(self):
        url = reverse("void:alerttrigger-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ids = [t["id"] for t in response.data["results"]]
        self.assertIn(self.trigger.pk, ids)

    def test_trigger_read_only(self):
        url = reverse("void:alerttrigger-list")
        response = self.client.post(url, {
            "rule": self.rule.pk,
            "event": self.event.pk,
            "message": "Hacked",
        }, format="json")
        self.assertEqual(response.status_code, 405)

    def test_dispatch_now_action(self):
        url = reverse("void:alerttrigger-dispatch-now", kwargs={"pk": self.trigger.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.trigger.refresh_from_db()
        self.assertEqual(self.trigger.status, "dispatched")

    def test_unauthenticated_access_denied(self):
        self.client.force_authenticate(user=None)
        url = reverse("void:alertrule-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)
