"""Tests for void replication service."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from void.models import Device, Point, ProcessedReading
from void.services import ReplicationService


class ReplicationServiceTests(TestCase):
    def setUp(self):
        self.point = Point.objects.create(
            name="P-Replicate",
            frequency_minutes=5,
            replicate_on_missing=True,
            max_replication_hours=24,
        )
        self.device = Device.objects.create(
            point=self.point,
            configuration={"variables": ["total"]},
        )

    def test_replicate_when_no_recent_data(self):
        """Genera lecturas replicadas si no hay datos recientes."""
        now = timezone.now()
        last_ts = now - timedelta(minutes=20)
        template = ProcessedReading.objects.create(
            device=self.device,
            variable="total",
            timestamp=last_ts,
            total=100,
            is_error=False,
        )

        created = ReplicationService().replicate_missing_for_point(
            self.point, "total", until=now
        )

        # Debe crear slots en +5, +10, +15, +20 minutos desde last_ts (hasta now).
        self.assertEqual(len(created), 4)
        self.assertEqual(ProcessedReading.objects.filter(variable="total").count(), 5)

        first = created[0]
        self.assertEqual(first.total, template.total)
        self.assertTrue(first.is_interpolated)
        self.assertEqual(first.extra_values.get("replicated_from"), template.id)

    def test_no_replicate_when_recent_data_exists(self):
        """No replica si ya hay un dato dentro del próximo slot esperado."""
        now = timezone.now()
        ProcessedReading.objects.create(
            device=self.device,
            variable="total",
            timestamp=now - timedelta(minutes=3),
            total=100,
            is_error=False,
        )

        created = ReplicationService().replicate_missing_for_point(
            self.point, "total", until=now
        )
        self.assertEqual(created, [])

    def test_no_replicate_when_disabled(self):
        """No replica si el punto tiene replicate_on_missing=False."""
        self.point.replicate_on_missing = False
        self.point.save(update_fields=["replicate_on_missing"])

        now = timezone.now()
        ProcessedReading.objects.create(
            device=self.device,
            variable="total",
            timestamp=now - timedelta(minutes=20),
            total=100,
            is_error=False,
        )

        created = ReplicationService().replicate_missing_for_point(
            self.point, "total", until=now
        )
        self.assertEqual(created, [])

    def test_no_replicate_beyond_max_hours(self):
        """No replica si el último dato válido supera max_replication_hours."""
        self.point.max_replication_hours = 1
        self.point.save(update_fields=["max_replication_hours"])

        now = timezone.now()
        ProcessedReading.objects.create(
            device=self.device,
            variable="total",
            timestamp=now - timedelta(hours=2),
            total=100,
            is_error=False,
        )

        created = ReplicationService().replicate_missing_for_point(
            self.point, "total", until=now
        )
        self.assertEqual(created, [])
