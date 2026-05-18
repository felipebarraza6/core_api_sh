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
from django.core.cache import cache
from api.core.models import InteractionDetail, DgaDataConfigCatchment
from api.cronjobs.telemetry.controllers.flow import average_flow
from api.cronjobs.utils.logging_config import dga_logger


def calculate_daily_average_flow(
    register: InteractionDetail,
    dga_config: DgaDataConfigCatchment
) -> float:
    """
    Calcula el caudal medio diario para estándar MEDIO.
    
    Para estándar MEDIO, DGA requiere:
    - Caudal medio diario = Promedio de todas las horas del día anterior (00:00 a 23:59)
    
    Args:
        register: Registro de InteractionDetail a procesar
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
        fecha_medicion = register.date_time_medition
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
        
        # Cache key: punto + fecha del día anterior
        cache_key = f"dga_daily_flow:{register.catchment_point_id}:{dia_anterior_inicio.date().isoformat()}"
        cached_value = cache.get(cache_key)
        if cached_value is not None:
            return cached_value
        
        # Obtener todos los registros del día anterior
        yesterday_records = list(InteractionDetail.objects.filter(
            catchment_point=register.catchment_point,
            date_time_medition__gte=dia_anterior_inicio,
            date_time_medition__lte=dia_anterior_fin
        ).order_by('date_time_medition').select_related('catchment_point'))
        
        if not yesterday_records:
            # No hay registros del día anterior, cachear 0.0 y retornar
            cache.set(cache_key, 0.0, timeout=86400)
            return 0.0
        
        # Precargar todos los registros previos necesarios en una sola query
        # para eliminar N+1 dentro del loop
        prev_timestamps = [r.date_time_medition for r in yesterday_records if r.date_time_medition]
        if prev_timestamps:
            earliest = min(prev_timestamps)
            all_prev_records = list(InteractionDetail.objects.filter(
                catchment_point=register.catchment_point,
                date_time_medition__lt=max(prev_timestamps),
                date_time_medition__gte=earliest - timedelta(days=1)
            ).order_by('date_time_medition').only('date_time_medition', 'total'))
        else:
            all_prev_records = []
        
        # Crear lookup de registro anterior por timestamp
        prev_lookup = {}
        for i, record in enumerate(yesterday_records):
            if i > 0:
                prev_lookup[record.id] = yesterday_records[i - 1]
            else:
                # Buscar en precargados
                for prev in reversed(all_prev_records):
                    if prev.date_time_medition < record.date_time_medition:
                        prev_lookup[record.id] = prev
                        break
        
        # Calcular caudal para cada registro del día anterior
        caudales_del_dia = []
        
        for record in yesterday_records:
            if record.total_diff and record.total_diff > 0:
                previous_record = prev_lookup.get(record.id)
                
                if previous_record and previous_record.total and record.total:
                    try:
                        curr_ts = record.date_time_medition.astimezone(chile_tz)
                        prev_ts = previous_record.date_time_medition.astimezone(chile_tz)
                        dt = (curr_ts - prev_ts).total_seconds()
                        
                        if dt > 0:
                            curr_total = float(record.total)
                            prev_total = float(previous_record.total)
                            diff = curr_total - prev_total
                            
                            if diff > 0:
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
        
        if caudales_del_dia:
            promedio_diario = round(sum(caudales_del_dia) / len(caudales_del_dia), 2)
        else:
            promedio_diario = 0.0
        
        cache.set(cache_key, promedio_diario, timeout=86400)
        return promedio_diario
            
    except Exception as e:
        dga_logger.error(f"Error calculando caudal medio diario para registro {register.id}: {e}")
        return 0.0


def _calculate_dynamic_flow_fallback(register: InteractionDetail) -> float:
    """
    Función fallback que usa el cálculo actual (no modifica comportamiento existente).
    
    Esta función replica la lógica de _calculate_dynamic_flow() para mantener
    compatibilidad con otros estándares.
    """
    try:
        from api.cronjobs.dga.cron_dga import _calculate_dynamic_flow
        return _calculate_dynamic_flow(register)
    except Exception:
        # Si falla, usar valor guardado
        return float(register.flow) if register.flow else 0.0


def calculate_flow_by_standard(
    register: InteractionDetail,
    dga_config: DgaDataConfigCatchment
) -> float:
    """
    Calcula el caudal según el estándar DGA del punto.
    
    Esta función centraliza la lógica de cálculo según estándar:
    - MEDIO: Caudal medio diario (promedio de 24 horas del día anterior)
    - Otros: Cálculo actual (entre registro actual y anterior)
    
    Args:
        register: Registro de InteractionDetail
        dga_config: Configuración DGA
        
    Returns:
        float: Caudal calculado según estándar
    """
    if dga_config.standard == "MEDIO":
        return calculate_daily_average_flow(register, dga_config)
    else:
        # Para otros estándares, usar cálculo actual
        return _calculate_dynamic_flow_fallback(register)

