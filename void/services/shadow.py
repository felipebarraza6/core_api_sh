"""Shadow mode service: compare legacy InteractionDetail vs void readings."""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from void.models import Device, DeviceVariableConfig, ProcessedReading, RawReading, ShadowComparison, ShadowRun

logger = logging.getLogger(__name__)


class ShadowService:
    """Ejecuta shadow mode: replicar lectura legacy con void y comparar.

    Legacy genera registros horarios (InteractionDetail), mientras que void
    puede generar lecturas por minuto. Para una comparación justa, void se
    agrupa por hora y se usa el último valor de cada hora.
    """

    # Tolerancias recomendadas según campo. Legacy redondea totales a int,
    # por lo que 1.0 m³ es suficiente. Para variables crudas se usa 0.001.
    TOLERANCES = {
        "total": Decimal("1.0"),
        "flow": Decimal("0.01"),
        "nivel": Decimal("0.01"),
        "water_table": Decimal("0.01"),
    }

    def __init__(
        self,
        value_tolerance: Decimal = None,
        aggregation: str = "last",
    ):
        self.value_tolerance = value_tolerance or self.TOLERANCES["total"]
        self.aggregation = aggregation

    def run(
        self,
        device: Device,
        variable: str,
        output_field: str = "",
        window_minutes: int = 70,
        ingest: bool = True,
        process: bool = False,
    ) -> ShadowRun:
        """Ejecuta una comparación shadow para un device/variable.

        Args:
            device: dispositivo void (con legacy_point).
            variable: variable a comparar (ej: "pulses").
            output_field: si se indica (total, flow, nivel, water_table), compara
                el valor procesado de void contra el campo homólogo de legacy.
            window_minutes: ventana hacia atrás desde ahora.
            ingest: si True, obtiene datos del proveedor usando void.
            process: si True, procesa las lecturas crudas con PipelineService.
        """
        return self._run_impl(
            device=device,
            variable=variable,
            output_field=output_field,
            window_minutes=window_minutes,
            ingest=ingest,
            process=process,
        )

    def run_for_output_field(
        self,
        device: Device,
        output_field: str = "total",
        window_minutes: int = 70,
        ingest: bool = True,
        process: bool = False,
    ) -> ShadowRun:
        """Ejecuta shadow descubriendo la variable void por su campo de salida.

        Busca la ``DeviceVariableConfig`` activa del device cuyo ``output_field``
        coincida. Si no hay output_field explícito, usa ``internal_variable``.
        Eso mantiene la coherencia con void: no se asume que la variable interna
        se llame igual que el campo físico donde se guarda.
        """
        config = self._find_config_for_output(device, output_field)
        if config is None:
            until = timezone.now()
            since = until - timedelta(minutes=window_minutes)
            run = ShadowRun.objects.create(
                device=device,
                variable="",
                output_field=output_field,
                window_start=since,
                window_end=until,
                status="skipped",
                error_message=f"No hay config activa con output_field='{output_field}'.",
            )
            return run

        return self._run_impl(
            device=device,
            variable=config.internal_variable,
            output_field=output_field,
            window_minutes=window_minutes,
            ingest=ingest,
            process=process,
        )

    def _find_config_for_output(
        self,
        device: Device,
        output_field: str,
    ) -> Optional[DeviceVariableConfig]:
        """Devuelve la config activa que produce el campo de salida indicado."""
        configs = DeviceVariableConfig.objects.filter(
            device=device,
            is_active=True,
        )
        for config in configs:
            effective_output = config.output_field or config.internal_variable
            if effective_output == output_field:
                return config
        return None

    @transaction.atomic
    def _run_impl(
        self,
        device: Device,
        variable: str,
        output_field: str = "",
        window_minutes: int = 70,
        ingest: bool = True,
        process: bool = False,
    ) -> ShadowRun:
        """Implementación interna de shadow run."""
        until = timezone.now()
        since = until - timedelta(minutes=window_minutes)

        run = ShadowRun.objects.create(
            device=device,
            variable=variable,
            output_field=output_field,
            window_start=since,
            window_end=until,
            status="running",
        )

        try:
            if device.provider is None:
                run.status = "skipped"
                run.error_message = "Device no tiene proveedor void."
                run.save(update_fields=["status", "error_message"])
                return run

            legacy_point = device.point.legacy_point
            if legacy_point is None:
                run.status = "skipped"
                run.error_message = "Device no tiene punto legacy asociado."
                run.save(update_fields=["status", "error_message"])
                return run

            if ingest:
                self._ingest_void(device, variable, since, until)

            if process:
                self._process_void(device, variable, since, until)

            # Tolerancia según campo.
            self.value_tolerance = self.TOLERANCES.get(output_field, self.value_tolerance)

            if output_field:
                legacy_records = self._fetch_legacy_processed(
                    legacy_point, output_field, since, until
                )
                void_records = self._fetch_void_processed(
                    device, variable, output_field, since, until
                )
            else:
                legacy_records = self._fetch_legacy(legacy_point, variable, since, until)
                void_records = self._fetch_void(device, variable, since, until)

            self._compare(run, legacy_records, void_records)
            run.status = "completed"
            run.save(update_fields=["status"])

        except Exception as exc:
            logger.exception("Error en shadow run %s", run.id)
            run.status = "failed"
            run.error_message = str(exc)
            run.save(update_fields=["status", "error_message"])

        return run

    def _ingest_void(
        self,
        device: Device,
        variable: str,
        since: datetime,
        until: datetime,
    ) -> int:
        from void.services import IngestService

        service = IngestService()
        created = service.ingest_device_variable(
            device=device,
            variable=variable,
            since=since,
            until=until,
        )
        return len(created)

    def _process_void(
        self,
        device: Device,
        variable: str,
        since: datetime,
        until: datetime,
    ) -> int:
        from void.services import PipelineService

        service = PipelineService()
        results = service.process_device_variable(device, variable, since=since, until=until)
        return len(results)

    def _fetch_legacy(
        self,
        legacy_point,
        variable: str,
        since: datetime,
        until: datetime,
    ) -> List[Dict[str, Any]]:
        from api.core.models import InteractionDetail

        qs = InteractionDetail.objects.filter(
            catchment_point=legacy_point,
            date_time_medition__gte=since,
            date_time_medition__lte=until,
        ).order_by("date_time_medition")

        records = []
        for item in qs:
            raw = self._extract_legacy_value(item, variable=variable)
            records.append({
                "id": item.id,
                "timestamp": item.date_time_medition,
                "value": raw,
                "pulses": item.pulses,
                "total": item.total,
                "flow": item.flow,
                "nivel": item.nivel,
            })
        return records

    def _fetch_void(
        self,
        device: Device,
        variable: str,
        since: datetime,
        until: datetime,
    ) -> List[Dict[str, Any]]:
        qs = RawReading.objects.filter(
            device=device,
            variable=variable,
            timestamp__gte=since,
            timestamp__lte=until,
        ).order_by("timestamp")

        records = []
        for item in qs:
            records.append({
                "id": item.id,
                "timestamp": item.timestamp,
                "value": item.raw_value,
            })
        return records

    def _fetch_legacy_processed(
        self,
        legacy_point,
        output_field: str,
        since: datetime,
        until: datetime,
    ) -> List[Dict[str, Any]]:
        """Extrae registros legacy con el campo procesado solicitado."""
        from api.core.models import InteractionDetail

        qs = InteractionDetail.objects.filter(
            catchment_point=legacy_point,
            date_time_medition__gte=since,
            date_time_medition__lte=until,
        ).order_by("date_time_medition")

        records = []
        for item in qs:
            value = getattr(item, output_field, None)
            if value is None:
                continue
            records.append({
                "id": item.id,
                "timestamp": item.date_time_medition,
                "value": str(value),
            })
        return records

    def _fetch_void_processed(
        self,
        device: Device,
        variable: str,
        output_field: str,
        since: datetime,
        until: datetime,
    ) -> List[Dict[str, Any]]:
        """Extrae lecturas procesadas de void para el campo solicitado."""
        qs = ProcessedReading.objects.filter(
            device=device,
            variable=variable,
            timestamp__gte=since,
            timestamp__lte=until,
        ).order_by("timestamp")

        records = []
        for item in qs:
            value = getattr(item, output_field, None)
            if value is None:
                value = (item.extra_values or {}).get(output_field)
            if value is None:
                continue
            records.append({
                "id": item.id,
                "timestamp": item.timestamp,
                "value": str(value),
            })
        return records

    def _extract_legacy_value(self, interaction, variable: str = "") -> str:
        """Extrae el valor crudo de variable_values si existe; si no, usa pulses.

        Si ``variable`` coincide con una variable legacy del punto, busca su
        valor en ``variable_values`` por ID. Si no hay coincidencia pero
        ``variable_values`` tiene exactamente una clave numérica, usa ese valor
        como fallback (compatibilidad con tests y registros antiguos). De lo
        contrario retorna ``interaction.pulses``.
        """
        variable_values = interaction.variable_values or {}

        if variable_values and variable and interaction.catchment_point_id:
            try:
                from api.core.models import Variable
                legacy_var = Variable.objects.filter(
                    scheme_catchment__catchment_point_id=interaction.catchment_point_id,
                    str_variable=variable,
                ).first()
                if legacy_var and str(legacy_var.id) in variable_values:
                    return str(variable_values[str(legacy_var.id)])
            except Exception:
                pass

            # Fallback: un único valor numérico en variable_values.
            numeric_keys = [k for k in variable_values.keys() if str(k).isdigit()]
            if len(numeric_keys) == 1:
                return str(variable_values[numeric_keys[0]])

        return str(interaction.pulses)

    def _compare(
        self,
        run: ShadowRun,
        legacy_records: List[Dict[str, Any]],
        void_records: List[Dict[str, Any]],
    ) -> None:
        run.legacy_count = len(legacy_records)
        run.void_count = len(void_records)

        legacy_by_hour = {self._hour_key(r["timestamp"]): r for r in legacy_records}
        void_by_hour = self._aggregate_void_by_hour(void_records)

        all_hours = set(legacy_by_hour.keys()) | set(void_by_hour.keys())

        comparisons = []
        for hour in sorted(all_hours):
            legacy = legacy_by_hour.get(hour)
            void = void_by_hour.get(hour)

            if legacy and void:
                result, diff = self._values_match(legacy["value"], void["value"])
                comparisons.append(ShadowComparison(
                    run=run,
                    timestamp=legacy["timestamp"],
                    result=result,
                    legacy_value=legacy["value"],
                    void_value=void["value"],
                    legacy_record_id=str(legacy["id"]),
                    void_record_id=str(void["id"]),
                    diff={
                        **diff,
                        "void_readings_in_hour": void.get("count", 1),
                        "void_timestamp": void["timestamp"].isoformat() if void.get("timestamp") else None,
                    },
                ))
                if result == "match":
                    run.matched_count += 1
                else:
                    run.mismatched_count += 1
            elif legacy:
                comparisons.append(ShadowComparison(
                    run=run,
                    timestamp=legacy["timestamp"],
                    result="legacy_only",
                    legacy_value=legacy["value"],
                    legacy_record_id=str(legacy["id"]),
                ))
                run.legacy_only_count += 1
            else:
                comparisons.append(ShadowComparison(
                    run=run,
                    timestamp=void["timestamp"],
                    result="void_only",
                    void_value=void["value"],
                    void_record_id=str(void["id"]),
                    diff={"void_readings_in_hour": void.get("count", 1)},
                ))
                run.void_only_count += 1

        ShadowComparison.objects.bulk_create(comparisons)
        run.save(update_fields=[
            "legacy_count", "void_count", "matched_count",
            "mismatched_count", "legacy_only_count", "void_only_count",
        ])

    def _aggregate_void_by_hour(
        self,
        void_records: List[Dict[str, Any]],
    ) -> Dict[Tuple[int, int, int, int], Dict[str, Any]]:
        """Agrupa lecturas void por hora y retorna el último valor (por defecto)."""
        groups = defaultdict(list)
        for record in void_records:
            groups[self._hour_key(record["timestamp"])].append(record)

        aggregated = {}
        for hour, records in groups.items():
            if self.aggregation == "last":
                chosen = records[-1]
            elif self.aggregation == "first":
                chosen = records[0]
            elif self.aggregation == "avg":
                values = [self._to_decimal(r["value"]) for r in records]
                values = [v for v in values if v is not None]
                avg = sum(values, Decimal(0)) / len(values) if values else Decimal(0)
                chosen = {
                    "id": records[-1]["id"],
                    "timestamp": records[-1]["timestamp"],
                    "value": str(avg),
                }
            else:
                chosen = records[-1]

            aggregated[hour] = {
                **chosen,
                "count": len(records),
            }
        return aggregated

    @staticmethod
    def _hour_key(dt: datetime) -> Tuple[int, int, int, int]:
        """Clave única por hora (año, mes, día, hora)."""
        return (dt.year, dt.month, dt.day, dt.hour)

    def _values_match(self, legacy_value: str, void_value: str) -> Tuple[str, Dict[str, Any]]:
        """Compara dos valores numéricos dentro de tolerancia."""
        legacy_dec = self._to_decimal(legacy_value)
        void_dec = self._to_decimal(void_value)

        if legacy_dec is None or void_dec is None:
            return ("mismatch", {"reason": "non_numeric", "legacy": legacy_value, "void": void_value})

        diff = abs(legacy_dec - void_dec)
        if diff <= self.value_tolerance:
            return ("match", {"diff": str(diff)})

        return ("mismatch", {
            "diff": str(diff),
            "legacy": str(legacy_dec),
            "void": str(void_dec),
        })

    @staticmethod
    def _to_decimal(value: Any) -> Optional[Decimal]:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError):
            return None
