"""Tests for void models."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from void.models import (
    Device,
    DeviceHardware,
    Point,
    PointGroup,
    ProcessingSchema,
    ProcessingStep,
    SLAEvent,
    SLAPolicy,
    VoidUserProfile,
)


User = get_user_model()


class VoidUserProfileTests(TestCase):
    def test_create_profile(self):
        user = User.objects.create_user(
            email="void@smarthydro.cl",
            username="void_user",
            password="testpass123",
            first_name="Void",
            last_name="User",
        )
        profile = VoidUserProfile.objects.create(
            user=user,
            role="operator",
            phone="+56912345678",
        )
        self.assertEqual(str(profile), f"{user.email} (operator)")
        self.assertTrue(profile.is_active)


class PointTests(TestCase):
    def test_create_point(self):
        point = Point.objects.create(
            name="Punto de prueba",
            code_internal="PT-001",
            client="Cliente A",
            project="Proyecto X",
            frequency_minutes=5,
            migration_status="not_started",
        )
        self.assertEqual(str(point), "Punto de prueba (PT-001)")
        self.assertTrue(point.is_active)

    def test_point_group_permissions(self):
        point = Point.objects.create(name="P1")
        group = PointGroup.objects.create(name="Grupo Norte")
        group.points.add(point)
        self.assertIn(point, group.points.all())


class DeviceTests(TestCase):
    def test_create_device(self):
        point = Point.objects.create(name="P1")
        device = Device.objects.create(
            point=point,
            external_id="ext-123",
            serial_number="SN-123",
            configuration={"variables": ["pulses"]},
        )
        self.assertEqual(device.point, point)
        self.assertTrue(device.is_active)

    def test_hardware_inventory(self):
        point = Point.objects.create(name="P1")
        device = Device.objects.create(point=point)
        hw = DeviceHardware.objects.create(
            device=device,
            component_type="logger",
            serial="LOG-001",
            status="active",
        )
        self.assertEqual(hw.component_type, "logger")
        self.assertIn(hw, device.hardware.all())


class ProcessingSchemaTests(TestCase):
    def test_create_schema_with_steps(self):
        schema = ProcessingSchema.objects.create(
            name="Esquema básico",
            version="1.0",
            applies_to={"providers": ["tdata"]},
        )
        step = ProcessingStep.objects.create(
            schema=schema,
            order=1,
            step_type="filter",
            name="Filtrar negativos",
            configuration={"min_value": 0, "action": "drop"},
        )
        self.assertEqual(schema.steps.count(), 1)
        self.assertIn(step, schema.steps.all())


class SLAPolicyTests(TestCase):
    def test_create_policy_and_event(self):
        policy = SLAPolicy.objects.create(
            name="Batería baja",
            metric="battery_level",
            operator="<",
            threshold=20,
            severity="critical",
        )
        point = Point.objects.create(name="P1")
        device = Device.objects.create(point=point)
        event = SLAEvent.objects.create(
            policy=policy,
            device=device,
            started_at="2026-01-01T00:00:00Z",
            status="open",
            observed_value=15,
        )
        self.assertEqual(str(policy), "Batería baja: battery_level < 20")
        self.assertEqual(event.status, "open")
