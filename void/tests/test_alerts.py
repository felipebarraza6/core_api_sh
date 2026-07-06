"""Tests for void alert engine."""
import uuid

from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone

from void.models import (
    AlertRule,
    AlertTrigger,
    Device,
    DeviceEvent,
    Point,
)
from void.services.alerts import AlertEngine
from void.services.notifications import AlertDispatcher
from void.signals import evaluate_device_event_alert


class AlertEngineTests(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.point = Point.objects.create(name=f"P-Alert-{self.suffix}")
        self.device = Device.objects.create(point=self.point, configuration={})
        # Desconectar señal para probar el engine en aislamiento.
        post_save.disconnect(evaluate_device_event_alert, sender=DeviceEvent)
        self.addCleanup(
            post_save.connect, evaluate_device_event_alert, sender=DeviceEvent
        )

    def test_rule_matches_event_type(self):
        rule = AlertRule.objects.create(
            name=f"Reset alert {self.suffix}",
            event_types=["counter_reset"],
            channels=["in_app"],
        )
        event = DeviceEvent.objects.create(
            device=self.device,
            variable="pulses",
            event_type="counter_reset",
            severity="warning",
            timestamp=timezone.now(),
        )
        triggers = AlertEngine().evaluate_event(event)
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].rule, rule)
        event.refresh_from_db()
        self.assertTrue(event.is_dispatched)

    def test_rule_filters_by_severity(self):
        AlertRule.objects.create(
            name=f"Critical only {self.suffix}",
            event_types=["massive_jump"],
            severities=["critical"],
            channels=["in_app"],
        )
        event = DeviceEvent.objects.create(
            device=self.device,
            variable="pulses",
            event_type="massive_jump",
            severity="warning",
            timestamp=timezone.now(),
        )
        triggers = AlertEngine().evaluate_event(event)
        self.assertEqual(len(triggers), 0)

    def test_rule_filters_by_device(self):
        other_point = Point.objects.create(name=f"P-Alert-Other-{self.suffix}")
        other_device = Device.objects.create(point=other_point, configuration={})
        AlertRule.objects.create(
            name=f"Device specific {self.suffix}",
            event_types=["device_offline"],
            device_ids=[self.device.pk],
            channels=["in_app"],
        )
        event = DeviceEvent.objects.create(
            device=other_device,
            variable="pulses",
            event_type="device_offline",
            severity="critical",
            timestamp=timezone.now(),
        )
        triggers = AlertEngine().evaluate_event(event)
        self.assertEqual(len(triggers), 0)

    def test_cooldown_prevents_duplicate(self):
        rule = AlertRule.objects.create(
            name=f"Cooldown {self.suffix}",
            event_types=["counter_reset"],
            cooldown_minutes=60,
            channels=["in_app"],
        )
        t1 = timezone.now()
        event1 = DeviceEvent.objects.create(
            device=self.device,
            variable="pulses",
            event_type="counter_reset",
            severity="warning",
            timestamp=t1,
        )
        AlertEngine().evaluate_event(event1)

        event2 = DeviceEvent.objects.create(
            device=self.device,
            variable="pulses",
            event_type="counter_reset",
            severity="warning",
            timestamp=t1,
        )
        triggers = AlertEngine().evaluate_event(event2)
        self.assertEqual(len(triggers), 0)

    def test_event_already_dispatched_is_ignored(self):
        AlertRule.objects.create(
            name=f"Ignore dispatched {self.suffix}",
            event_types=["counter_reset"],
            channels=["in_app"],
        )
        event = DeviceEvent.objects.create(
            device=self.device,
            variable="pulses",
            event_type="counter_reset",
            severity="warning",
            timestamp=timezone.now(),
            is_dispatched=True,
        )
        triggers = AlertEngine().evaluate_event(event)
        self.assertEqual(len(triggers), 0)


class AlertDispatcherTests(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.point = Point.objects.create(name=f"P-Dispatch-{self.suffix}")
        self.device = Device.objects.create(point=self.point, configuration={})
        self.rule = AlertRule.objects.create(
            name=f"Email alert {self.suffix}",
            event_types=["counter_reset"],
            channels=["in_app", "email"],
            recipients={"emails": ["test@smarthydro.cl"]},
        )
        # Desconectar señal para evitar triggers extra en estos tests unitarios.
        post_save.disconnect(evaluate_device_event_alert, sender=DeviceEvent)
        self.addCleanup(
            post_save.connect, evaluate_device_event_alert, sender=DeviceEvent
        )
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
            message="Test alert",
        )

    def test_dispatch_in_app_marks_sent(self):
        dispatcher = AlertDispatcher()
        result = dispatcher.dispatch(self.trigger)
        self.trigger.refresh_from_db()
        self.assertEqual(self.trigger.status, "dispatched")
        self.assertIsNotNone(self.trigger.dispatched_at)
        self.assertIn("in_app", result)

    def test_dispatch_email_fails_without_backend(self):
        self.trigger.channels = ["email"]
        self.trigger.save()
        dispatcher = AlertDispatcher()
        result = dispatcher.dispatch(self.trigger)
        self.trigger.refresh_from_db()
        self.assertEqual(self.trigger.status, "failed")
        self.assertIn("email", result)

    def test_dispatch_pending_batch(self):
        dispatcher = AlertDispatcher()
        stats = dispatcher.dispatch_pending(limit=10)
        self.assertEqual(stats["processed"], 1)
        self.assertEqual(stats["dispatched"], 1)
        self.assertTrue(
            AlertTrigger.objects.filter(pk=self.trigger.pk, status="dispatched").exists()
        )


class AlertSignalTests(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.point = Point.objects.create(name=f"P-Signal-{self.suffix}")
        self.device = Device.objects.create(point=self.point, configuration={})

    def test_signal_creates_trigger_on_event_creation(self):
        AlertRule.objects.create(
            name=f"Signal rule {self.suffix}",
            event_types=["counter_reset"],
            channels=["in_app"],
        )
        event = DeviceEvent.objects.create(
            device=self.device,
            variable="pulses",
            event_type="counter_reset",
            severity="warning",
            timestamp=timezone.now(),
        )
        event.refresh_from_db()
        self.assertTrue(event.is_dispatched)
        self.assertEqual(
            AlertTrigger.objects.filter(event=event, rule__name__contains=self.suffix).count(),
            1,
        )
