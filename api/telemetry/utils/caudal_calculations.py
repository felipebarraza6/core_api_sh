"""
Funciones de cálculo de caudal según estándar DGA.

IMPORTANTE: Estas funciones son NUEVAS y no modifican el código existente.
Se implementan para corregir el cálculo de caudal medio diario para estándar MEDIO.

Antes de usar en producción, deben validarse exhaustivamente.
"""
from datetime import datetime, timedelta
from typing import Optional
import pytz

from django.db.models import Avg, Q
from api.core.models import TelemetryRecord, DgaDataConfigCatchment
from api.telemetry.ingestion.controllers.flow import average_flow


def calculate_daily_average_flow(
    register: TelemetryRecord, dga_config: DgaDataConfigCatchment
) -> float:
    """
    Calcula el caudal medio diario para estándar MEDIO.

    Para estándar MEDIO, DGA requiere:
    - Caudal medio diario = Promedio de todas las horas del día anterior (00:00 a 23:59)

    Args:
        register: Registro de TelemetryRecord a procesar
        dga_config: Configuración DGA del punto

    Returns:
        float: Caudal medio diario en L/s, o 0.0 si no se puede calcular
    """
    if dga_config.standard != "MEDIO":
        # Para otros estándares, usar cálculo actual (no modificar comportamiento)
        return _calculate_dynamic_flow_fallback(register)

    try:
        chile_tz = pytz.timezone("America/Santiago")

        # Obtener fecha de medición del registro
        fecha_medicion = register.timestamp
        if not fecha_medicion:
            return 0.0

        fecha_medicion = fecha_medicion.astimezone(chile_tz)

        # Calcular día anterior (00:00 a 23:59)
        dia_anterior_inicio = (fecha_medicion - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        dia_anterior_fin = (fecha_medicion - timedelta(days=1)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        # Obtener todos los registros del día anterior
        yesterday_records = (
            TelemetryRecord.objects.filter(
                point=register.point,
                timestamp__gte=dia_anterior_inicio,
                timestamp__lte=dia_anterior_fin,
            )
            .order_by("timestamp")
            .only("timestamp", "data", "point")
        )

        if not yesterday_records.exists():
            # No hay registros del día anterior, retornar 0.0
            return 0.0

        # Calcular caudal para cada registro del día anterior
        caudales_del_dia = []

        for record in yesterday_records:
            total_diff = float(record.data.get("total_diff", 0))

            # Si tiene consumo, calcular caudal basado en el registro anterior
            if total_diff > 0:
                # Buscar registro anterior a este
                previous_record = (
                    TelemetryRecord.objects.filter(
                        point=record.point, timestamp__lt=record.timestamp
                    )
                    .order_by("-timestamp")
                    .only("timestamp", "data")
                    .first()
                )

                if (
                    previous_record
                    and previous_record.data.get("total") is not None
                    and record.data.get("total") is not None
                ):
                    try:
                        # Calcular diferencia de tiempo
                        curr_ts = record.timestamp.astimezone(chile_tz)
                        prev_ts = previous_record.timestamp.astimezone(chile_tz)
                        dt = (curr_ts - prev_ts).total_seconds()

                        if dt > 0:
                            # Calcular diferencia de total
                            curr_total = float(record.data.get("total"))
                            prev_total = float(previous_record.data.get("total"))
                            diff = curr_total - prev_total

                            if diff > 0:
                                # Calcular caudal: (diff m³ / dt seg) * 1000 = L/s
                                caudal = (diff / dt) * 1000.0
                                if 0 <= abs(caudal) < 1000:
                                    caudales_del_dia.append(caudal)
                            else:
                                caudales_del_dia.append(0.0)
                        else:
                            caudales_del_dia.append(0.0)
                    except (ValueError, TypeError, AttributeError):
                        caudales_del_dia.append(0.0)
            else:
                caudales_del_dia.append(0.0)

        # Calcular promedio
        if caudales_del_dia:
            promedio_diario = sum(caudales_del_dia) / len(caudales_del_dia)
            return round(promedio_diario, 2)
        else:
            return 0.0

    except Exception as e:
        print(f"Error calculando caudal medio diario para registro {register.id}: {e}")
        return 0.0


def _calculate_dynamic_flow_fallback(register: TelemetryRecord) -> float:
    """
    Función fallback que usa el valor almacenado en data['flow'].
    """
    try:
        # En V3, el caudal ya viene calculado y almacenado en el JSON data
        # por el proceso de ingestión unificado.
        data = register.data
        return float(data.get("flow", data.get("caudal", 0)))
    except Exception:
        return 0.0


def calculate_flow_by_standard(
    register: TelemetryRecord, dga_config: DgaDataConfigCatchment
) -> float:
    """
    Calcula el caudal según el estándar DGA del punto.
    """
    if dga_config.standard == "MEDIO":
        return calculate_daily_average_flow(register, dga_config)
    else:
        return _calculate_dynamic_flow_fallback(register)

