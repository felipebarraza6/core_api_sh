"""Ingest service for void telemetry."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from void.models import Device, RawReading

from .providers.registry import registry


class IngestService:
    """Servicio de ingesta de lecturas crudas.

    Separa la obtención de datos del procesamiento, permitiendo probar
    cada capa de forma independiente.
    """

    def ingest_device_variable(
        self,
        device: Device,
        variable: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        task_id: str = "",
    ) -> List[RawReading]:
        """Ingesta lecturas de una variable para un dispositivo.

        Si el device no tiene provider o el handler no está registrado,
        retorna lista vacía y no falla.

        Las lecturas se deduplican por ``device + variable + timestamp``;
        si ya existe un ``RawReading`` con la misma clave se omite,
        evitando duplicados que descalabran totalizadores stateful.
        """
        if device.provider is None:
            return []

        provider = registry.build(device.provider)

        records: List[Dict[str, Any]] = provider.fetch(
            device=device,
            variable=variable,
            since=since,
            until=until,
        )

        created = []
        for record in records:
            timestamp = record["timestamp"]
            raw_value = str(record["value"])

            existing = RawReading.objects.filter(
                device=device,
                variable=variable,
                timestamp=timestamp,
            ).first()
            if existing is not None:
                continue

            raw = RawReading.objects.create(
                device=device,
                variable=variable,
                timestamp=timestamp,
                raw_value=raw_value,
                unit=record.get("unit", ""),
                provider_payload=record.get("payload", {}),
                ingest_task_id=task_id,
                is_valid=record.get("is_valid", True),
                validation_error=record.get("validation_error", ""),
            )
            created.append(raw)
        return created

    def ingest_reading(
        self,
        device: Device,
        variable: str,
        timestamp: datetime,
        value: Any,
        unit: str = "",
        payload: Optional[Dict[str, Any]] = None,
        task_id: str = "",
    ) -> RawReading:
        """Ingesta una lectura individual (útil para backfill o webhooks)."""
        return RawReading.objects.create(
            device=device,
            variable=variable,
            timestamp=timestamp,
            raw_value=str(value),
            unit=unit,
            provider_payload=payload or {},
            ingest_task_id=task_id,
        )
