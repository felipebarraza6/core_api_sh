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
from api.core.models import InteractionDetail, DgaDataConfigCatchment
from api.cronjobs.telemetry.controllers.flow import average_flow


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
        
        # Obtener todos los registros del día anterior
        yesterday_records = InteractionDetail.objects.filter(
            catchment_point=register.catchment_point,
            date_time_medition__gte=dia_anterior_inicio,
            date_time_medition__lte=dia_anterior_fin
        ).order_by('date_time_medition')
        
        if not yesterday_records.exists():
            # No hay registros del día anterior, retornar 0.0
            return 0.0
        
        # Calcular caudal para cada registro del día anterior
        # Para un promedio diario real de 24 horas, debemos incluir los periodos sin consumo (0.0 L/s)
        caudales_del_dia = []
        
        for record in yesterday_records:
            # Si tiene consumo, calcular caudal basado en el registro anterior
            if record.total_diff and record.total_diff > 0:
                # Buscar registro anterior a este
                previous_record = InteractionDetail.objects.filter(
                    catchment_point=record.catchment_point,
                    date_time_medition__lt=record.date_time_medition
                ).order_by('-date_time_medition').first()
                
                if previous_record and previous_record.total and record.total:
                    try:
                        # Calcular diferencia de tiempo
                        curr_ts = record.date_time_medition.astimezone(chile_tz)
                        prev_ts = previous_record.date_time_medition.astimezone(chile_tz)
                        dt = (curr_ts - prev_ts).total_seconds()
                        
                        if dt > 0:
                            # Calcular diferencia de total
                            curr_total = float(record.total)
                            prev_total = float(previous_record.total)
                            diff = curr_total - prev_total
                            
                            if diff > 0:
                                # Calcular caudal: (diff m³ / dt seg) * 1000 = L/s
                                caudal = (diff / dt) * 1000.0
                                if 0 <= abs(caudal) < 1000:  # Validar rango (permite 0)
                                    caudales_del_dia.append(caudal)
                            else:
                                caudales_del_dia.append(0.0)
                        else:
                            caudales_del_dia.append(0.0)
                    except (ValueError, TypeError, AttributeError):
                        caudales_del_dia.append(0.0)
            else:
                # Si no hay consumo (total_diff = 0), el caudal es 0.0
                # Pero lo incluimos en el promedio diario para que sea representativo de las 24h
                caudales_del_dia.append(0.0)
        
        # Calcular promedio de todos los registros del día (representativo de las 24 horas)
        if caudales_del_dia:
            promedio_diario = sum(caudales_del_dia) / len(caudales_del_dia)
            return round(promedio_diario, 2)
        else:
            return 0.0
            
    except Exception as e:
        # En caso de error, retornar 0.0 (no romper el proceso)
        print(f"Error calculando caudal medio diario para registro {register.id}: {e}")
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

