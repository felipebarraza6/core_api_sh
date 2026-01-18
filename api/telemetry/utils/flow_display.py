import logging
from datetime import datetime

from api.core.models import DgaDataConfigCatchment, Variable
from api.telemetry.ingestion.controllers.flow import average_flow

from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=128)
def _get_cached_point_config(cp_id):
    """
    Caché a nivel de proceso para configuraciones estáticas del punto.
    Esto acelera drásticamente el Admin y Serializers.
    """
    has_avg_flow = Variable.objects.filter(
        point_id=cp_id,
        internal_code__in=["caudal_promedio", "flow_avg", "avg_flow"],
        is_active=True,
    ).exists()
    
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=cp_id).first()
    
    return {
        "has_avg_flow": has_avg_flow,
        "dga_config": dga_config
    }

def get_interaction_flow_display_data(instance, cached_config=None):
    """
    Centraliza la lógica para obtener el caudal a mostrar (dinámico o guardado).
    Retorna un dict con:
    - value: float
    - type: str (INSTANTANEO, MEDIO, MEDIO_DIARIO)
    - is_calculated: bool

    Args:
        instance: TelemetryRecord object
        cached_config: Optional dict with keys: 'has_avg_flow', 'dga_config', 'standard'
    """
    catchment_point = instance.point
    cp_id = catchment_point.id

    # 1. Obtener configuración (de argumento, lru_cache o BD)
    if not cached_config:
        cached_config = _get_cached_point_config(cp_id)

    has_avg_flow = cached_config.get("has_avg_flow", False)

    flow_val = float(instance.data.get("flow", instance.data.get("caudal", 0)))

    if not has_avg_flow:
        return {"value": flow_val, "type": "INSTANTANEO", "is_calculated": False}

    # 2. Lógica especial para estándar MEDIO (DGA)
    from django.conf import settings

    use_new_calculation = getattr(settings, "USE_NEW_CAUDAL_CALCULATION_MEDIO", False)

    if use_new_calculation:
        dga_config = cached_config.get("dga_config")

        if dga_config and dga_config.standard == "MEDIO":
            try:
                from api.telemetry.utils.caudal_calculations import (
                    calculate_daily_average_flow,
                )

                avg_flow = calculate_daily_average_flow(instance, dga_config)
                return {"value": avg_flow, "type": "MEDIO_DIARIO", "is_calculated": True}
            except Exception:
                pass

    # 3. Lógica para otros estándares con CAUDAL_PROMEDIO (Cálculo horario)
    try:
        curr_ts = instance.timestamp

        if curr_ts:
            total_val = float(instance.data.get("total", 0))
            last_logger_ts = instance.metadata.get("last_logger_timestamp")

            if isinstance(last_logger_ts, str):
                try:
                    last_logger_ts = datetime.strptime(
                        last_logger_ts, "%Y-%m-%dT%H:%M:%S"
                    )
                except ValueError:
                    last_logger_ts = None

            # Re-usar average_flow del controlador
            calculated_flow = average_flow(
                point_catchment={"id": catchment_point.id},
                total=total_val,
                date_lg=curr_ts,
                exclude_id=instance.pk,
                current_logger_dt=last_logger_ts,
            )

            if calculated_flow > 0:
                return {
                    "value": calculated_flow,
                    "type": "MEDIO",
                    "is_calculated": True,
                }
    except Exception as e:
        logger.exception(
            "Error calculando caudal promedio dinámico",
            extra={
                "point_id": catchment_point.id,
                "date": instance.timestamp,
                "error": str(e),
            },
        )

    # Fallback al valor guardado
    return {"value": flow_val, "type": "MEDIO", "is_calculated": False}
