import logging
import pytz
from api.core.models import Variable, DgaDataConfigCatchment
from api.cronjobs.telemetry.controllers.flow import average_flow, _PREV_UNSET

from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=128)
def _get_cached_point_config(cp_id):
    """
    Caché a nivel de proceso para configuraciones estáticas del punto.
    Esto acelera drásticamente el Admin y Serializers.
    """
    from api.core.models import Variable, DgaDataConfigCatchment
    avg_var = Variable.objects.filter(
        type_variable="CAUDAL_PROMEDIO",
        scheme_catchment__points_catchment=cp_id,
    ).first()

    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=cp_id).first()
    
    return {
        "has_avg_flow": avg_var is not None,
        # False => el cron NUNCA escribe InteractionDetail.flow, así que el
        # valor hay que calcularlo en el momento (ver help_text del campo).
        "store_average_flow": bool(avg_var.store_average_flow) if avg_var else True,
        "dga_config": dga_config
    }

def get_interaction_flow_display_data(instance, cached_config=None,
                                      previous=_PREV_UNSET, quiet=False):
    """
    Centraliza la lógica para obtener el caudal a mostrar (dinámico o guardado).
    Retorna un dict con:
    - value: float
    - type: str (INSTANTANEO, MEDIO, MEDIO_DIARIO)
    - is_calculated: bool
    
    Args:
        instance: InteractionDetail object
        cached_config: Optional dict with keys: 'has_avg_flow', 'dga_config', 'standard'
        previous: registro anterior ya resuelto (ver average_flow) — evita
            1 query por registro en endpoints que devuelven muchas filas.
        quiet: silencia logs y SystemEvent de los guards de average_flow.
            Las rutas de lectura (GET) deben usarlo: los eventos ya se
            emiten en el ingest, aquí solo se está renderizando.
    """
    cp_id = instance.catchment_point_id
    
    # 1. Obtener configuración (de argumento, lru_cache o BD)
    if not cached_config:
        cached_config = _get_cached_point_config(cp_id)

    has_avg_flow = cached_config.get("has_avg_flow", False)
    
    if not has_avg_flow:
        return {
            "value": float(instance.flow) if instance.flow else 0.0,
            "type": "INSTANTANEO",
            "is_calculated": False
        }
    
    # 2. Lógica especial para estándar MEDIO (DGA)
    from django.conf import settings
    use_new_calculation = getattr(settings, 'USE_NEW_CAUDAL_CALCULATION_MEDIO', False)
    
    if use_new_calculation:
        dga_config = cached_config.get("dga_config")
            
        if dga_config and dga_config.standard == "MEDIO":
            try:
                from api.cronjobs.dga.caudal_calculations import calculate_daily_average_flow
                avg_flow = calculate_daily_average_flow(instance, dga_config)
                return {
                    "value": avg_flow,
                    "type": "MEDIO_DIARIO",
                    "is_calculated": True
                }
            except Exception:
                pass

    # 3. Lógica para otros estándares con CAUDAL_PROMEDIO (Cálculo horario)
    try:
        chile_tz = pytz.timezone("America/Santiago")
        # Usar preferentemente date_time_medition para consistencia con filtros
        curr_ts = instance.date_time_medition
        
        if curr_ts:
            # Re-usar average_flow del controlador
            calculated_flow = average_flow(
                point_catchment={"id": cp_id},
                total=float(instance.total) if instance.total else 0.0,
                date_lg=curr_ts,
                exclude_id=instance.pk,
                current_logger_dt=instance.date_time_last_logger,
                previous=previous,
                quiet=quiet,
            )
            
            if calculated_flow > 0:
                return {
                    "value": calculated_flow,
                    "type": "MEDIO",
                    "is_calculated": True
                }
    except Exception as e:
        logger.exception(
            "Error calculando caudal promedio dinámico",
            extra={
                'point_id': instance.catchment_point_id,
                'date': instance.date_time_medition,
                'error': str(e)
            }
        )

    # Fallback al valor guardado
    return {
        "value": float(instance.flow) if instance.flow else 0.0,
        "type": "MEDIO",
        "is_calculated": False
    }
