"""Replication service for void telemetry.

Cuando un punto tiene ``replicate_on_missing=True`` y no llegan lecturas
del proveedor, este servicio genera ``ProcessedReading`` sintéticos a partir
del último dato válido, replicando el comportamiento legacy de Nettra.

 IMPORTANTE: no modifica datos legacy y no envía a DGA por sí solo.
El envío DGA sigue dependiendo de ``PointComplianceProfile`` y ``auto_send``.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from typing import List, Optional

from django.db import transaction
from django.utils import timezone

from void.models import Device, Point, ProcessedReading, RawReading

logger = logging.getLogger(__name__)


class ReplicationService:
    """Genera lecturas replicadas cuando un punto no reporta datos."""

    def __init__(self, max_replication_hours: Optional[int] = None):
        self.max_replication_hours = max_replication_hours

    def replicate_missing_for_point(
        self,
        point: Point,
        variable: str,
        until: Optional[timezone.datetime] = None,
    ) -> List[ProcessedReading]:
        """Replica el último ``ProcessedReading`` válido si no hay datos recientes.

        Args:
            point: punto a revisar.
            variable: variable interna (p.ej. "total", "flow", "nivel").
            until: timestamp de referencia (default: ahora).

        Returns:
            Lista de ``ProcessedReading`` sintéticos creados (puede ser vacía).
        """
        if not point.replicate_on_missing:
            return []

        try:
            device = point.device
        except Device.DoesNotExist:
            return []

        until = until or timezone.now()
        max_hours = self.max_replication_hours or point.max_replication_hours or 24
        since = until - timedelta(hours=max_hours)
        frequency = timedelta(minutes=point.frequency_minutes or 60)

        # Último dato válido en la ventana máxima permitida.
        last_valid = ProcessedReading.objects.filter(
            device=device,
            variable=variable,
            is_error=False,
            timestamp__gte=since,
            timestamp__lte=until,
        ).order_by("-timestamp").first()

        if last_valid is None:
            logger.info(
                "[REPLICATION] %s variable=%s: sin datos válidos en últimas %s horas.",
                point, variable, max_hours,
            )
            return []

        # Si ya existe un dato real dentro del próximo slot esperado, no replicamos.
        next_expected = last_valid.timestamp + frequency
        if next_expected > until:
            return []

        # Generar slots esperados desde la siguiente frecuencia hasta ``until``.
        return self._create_replicated_readings(
            device=device,
            variable=variable,
            template=last_valid,
            start_at=next_expected,
            until=until,
            frequency=frequency,
        )

    @transaction.atomic
    def _create_replicated_readings(
        self,
        device: Device,
        variable: str,
        template: ProcessedReading,
        start_at: timezone.datetime,
        until: timezone.datetime,
        frequency: timedelta,
    ) -> List[ProcessedReading]:
        """Crea ProcessedReading replicados a partir de un template."""
        created = []
        current = start_at

        while current <= until:
            existing = ProcessedReading.objects.filter(
                device=device,
                variable=variable,
                timestamp=current,
            ).first()

            if existing is None:
                replicated = ProcessedReading.objects.create(
                    device=device,
                    variable=variable,
                    timestamp=current,
                    pulses=template.pulses,
                    total=template.total,
                    flow=template.flow,
                    nivel=template.nivel,
                    water_table=template.water_table,
                    total_diff=Decimal(0),
                    total_today_diff=Decimal(0),
                    extra_values={
                        **(template.extra_values or {}),
                        "replicated_from": template.id,
                        "replicated_at": timezone.now().isoformat(),
                    },
                    is_interpolated=True,
                    is_error=False,
                    error_message="",
                    processed_at=timezone.now(),
                    processor_version="void.replication.v1",
                )
                created.append(replicated)

            current += frequency

        if created:
            logger.info(
                "[REPLICATION] %s variable=%s: %s lecturas replicadas desde %s",
                device.point, variable, len(created), template.timestamp,
            )
        return created

    def replicate_missing_for_device(
        self,
        device: Device,
        until: Optional[timezone.datetime] = None,
    ) -> dict:
        """Replica datos faltantes para todas las variables configuradas de un device."""
        point = device.point
        if not point.replicate_on_missing:
            return {"replicated": 0, "variables": []}

        variables = device.configuration.get("variables", [])
        total = 0
        touched = []
        for variable in variables:
            created = self.replicate_missing_for_point(point, variable, until=until)
            if created:
                total += len(created)
                touched.append(variable)

        return {"replicated": total, "variables": touched}
