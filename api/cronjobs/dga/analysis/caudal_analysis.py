"""
Análisis de cálculo de caudales para DGA - SOLO LECTURA, NO MODIFICA DATOS.

Este módulo analiza cómo se están calculando los caudales actualmente
y compara con lo que debería calcularse según el estándar DGA.

IMPORTANTE: Este módulo NO modifica ningún dato, solo analiza.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytz

from django.db.models import Q, Avg, Count
from api.core.models import (
    InteractionDetail,
    DgaDataConfigCatchment,
    CatchmentPoint
)


def analyze_current_caudal_calculation(register_id: int) -> Dict:
    """
    Analiza cómo se calcula el caudal actualmente para un registro.
    
    Args:
        register_id: ID del registro a analizar
        
    Returns:
        Dict con análisis del cálculo actual
    """
    try:
        register = InteractionDetail.objects.select_related(
            'catchment_point'
        ).get(id=register_id)
        
        dga_config = DgaDataConfigCatchment.objects.filter(
            point_catchment=register.catchment_point
        ).first()
        
        if not dga_config:
            return {
                "error": "No hay configuración DGA para este punto",
                "register_id": register_id
            }
        
        analysis = {
            "register_id": register_id,
            "point_id": register.catchment_point.id,
            "point_name": str(register.catchment_point),
            "standard": dga_config.standard if dga_config else None,
            "date_time_medition": register.date_time_medition.isoformat() if register.date_time_medition else None,
            "current_flow": float(register.flow) if register.flow else 0.0,
            "total": register.total,
            "total_diff": register.total_diff,
            "calculation_method": "unknown"
        }
        
        # Analizar método de cálculo actual
        if register.total_diff == 0:
            analysis["calculation_method"] = "forced_zero"
            analysis["reason"] = "total_diff es 0, caudal forzado a 0"
        else:
            # Verificar si tiene CAUDAL_PROMEDIO
            from api.core.models import Variable
            has_caudal_promedio = Variable.objects.filter(
                scheme_catchment__points_catchment=register.catchment_point,
                type_variable="CAUDAL_PROMEDIO"
            ).exists()
            
            if has_caudal_promedio:
                analysis["calculation_method"] = "dynamic_average_flow"
                analysis["has_caudal_promedio"] = True
                
                # Buscar registro anterior para entender el cálculo
                previous = InteractionDetail.objects.filter(
                    catchment_point=register.catchment_point,
                    date_time_medition__lt=register.date_time_medition
                ).order_by('-date_time_medition').first()
                
                if previous:
                    analysis["previous_register_id"] = previous.id
                    analysis["previous_total"] = previous.total
                    analysis["time_difference_seconds"] = (
                        register.date_time_medition - previous.date_time_medition
                    ).total_seconds() if register.date_time_medition and previous.date_time_medition else None
            else:
                analysis["calculation_method"] = "stored_value"
                analysis["has_caudal_promedio"] = False
        
        return analysis
        
    except InteractionDetail.DoesNotExist:
        return {"error": "Registro no encontrado", "register_id": register_id}
    except Exception as e:
        return {"error": str(e), "register_id": register_id}


def analyze_medio_standard_requirements() -> Dict:
    """
    Analiza qué debería calcularse para estándar MEDIO.
    
    Para estándar MEDIO, DGA requiere:
    - Caudal medio diario (promedio de todas las horas del día anterior)
    
    Returns:
        Dict con análisis de requisitos
    """
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    
    # Día anterior
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = (now - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Obtener puntos con estándar MEDIO
    medio_points = DgaDataConfigCatchment.objects.filter(
        standard="MEDIO",
        send_dga=True
    ).select_related('point_catchment')
    
    analysis = {
        "standard": "MEDIO",
        "requirement": "Caudal medio diario (promedio de 24 horas del día anterior)",
        "analysis_date": now.isoformat(),
        "yesterday_start": yesterday_start.isoformat(),
        "yesterday_end": yesterday_end.isoformat(),
        "points_analyzed": [],
        "current_behavior": "Calcula caudal entre registro actual y anterior (no es promedio diario)",
        "required_behavior": "Calcular promedio de todos los caudales horarios del día anterior"
    }
    
    for dga_config in medio_points[:10]:  # Limitar a 10 para análisis
        point = dga_config.point_catchment
        
        # Obtener registros del día anterior
        yesterday_records = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=yesterday_start,
            date_time_medition__lte=yesterday_end
        ).order_by('date_time_medition')
        
        point_analysis = {
            "point_id": point.id,
            "point_name": str(point),
            "code_dga": dga_config.code_dga,
            "yesterday_records_count": yesterday_records.count(),
            "has_records": yesterday_records.exists()
        }
        
        if yesterday_records.exists():
            # Agrupar por hora y calcular promedio
            hourly_flows = []
            for record in yesterday_records:
                if record.flow and float(record.flow) > 0:
                    hourly_flows.append(float(record.flow))
            
            if hourly_flows:
                point_analysis["hourly_flows_count"] = len(hourly_flows)
                point_analysis["average_daily_flow"] = sum(hourly_flows) / len(hourly_flows)
                point_analysis["min_flow"] = min(hourly_flows)
                point_analysis["max_flow"] = max(hourly_flows)
            else:
                point_analysis["average_daily_flow"] = 0.0
                point_analysis["note"] = "No hay caudales válidos en el día anterior"
        
        analysis["points_analyzed"].append(point_analysis)
    
    return analysis


def compare_calculation_methods(register_id: int) -> Dict:
    """
    Compara el cálculo actual vs el cálculo requerido para estándar MEDIO.
    
    Args:
        register_id: ID del registro a analizar
        
    Returns:
        Dict con comparación de métodos
    """
    register = InteractionDetail.objects.select_related('catchment_point').get(id=register_id)
    dga_config = DgaDataConfigCatchment.objects.filter(
        point_catchment=register.catchment_point
    ).first()
    
    if not dga_config or dga_config.standard != "MEDIO":
        return {
            "error": "Este análisis es solo para estándar MEDIO",
            "register_id": register_id,
            "standard": dga_config.standard if dga_config else None
        }
    
    chile_tz = pytz.timezone("America/Santiago")
    fecha_medicion = register.date_time_medition.astimezone(chile_tz) if register.date_time_medition else None
    
    if not fecha_medicion:
        return {"error": "Registro sin fecha de medición", "register_id": register_id}
    
    # Día anterior
    dia_anterior_inicio = (fecha_medicion - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    dia_anterior_fin = (fecha_medicion - timedelta(days=1)).replace(
        hour=23, minute=59, second=59, microsecond=999999
    )
    
    # Método actual: caudal entre registro actual y anterior
    previous_register = InteractionDetail.objects.filter(
        catchment_point=register.catchment_point,
        date_time_medition__lt=register.date_time_medition
    ).order_by('-date_time_medition').first()
    
    current_method_flow = float(register.flow) if register.flow else 0.0
    
    # Método requerido: promedio diario del día anterior
    yesterday_records = InteractionDetail.objects.filter(
        catchment_point=register.catchment_point,
        date_time_medition__gte=dia_anterior_inicio,
        date_time_medition__lte=dia_anterior_fin
    ).order_by('date_time_medition')
    
    required_method_flows = []
    for record in yesterday_records:
        if record.flow and float(record.flow) > 0:
            required_method_flows.append(float(record.flow))
    
    required_method_flow = sum(required_method_flows) / len(required_method_flows) if required_method_flows else 0.0
    
    comparison = {
        "register_id": register_id,
        "point_id": register.catchment_point.id,
        "standard": "MEDIO",
        "fecha_medicion": fecha_medicion.isoformat(),
        "dia_anterior": {
            "inicio": dia_anterior_inicio.isoformat(),
            "fin": dia_anterior_fin.isoformat()
        },
        "current_method": {
            "flow": current_method_flow,
            "description": "Caudal entre registro actual y anterior",
            "previous_register_id": previous_register.id if previous_register else None
        },
        "required_method": {
            "flow": required_method_flow,
            "description": "Promedio de caudales del día anterior",
            "records_used": len(required_method_flows),
            "total_records_yesterday": yesterday_records.count()
        },
        "difference": abs(current_method_flow - required_method_flow),
        "difference_percent": (
            abs(current_method_flow - required_method_flow) / required_method_flow * 100
            if required_method_flow > 0 else 0
        )
    }
    
    return comparison

