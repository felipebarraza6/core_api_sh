"""
Validadores de coherencia para datos de telemetría (V3 Dinámico)
===============================================================

Este módulo contiene funciones para validar la coherencia de los datos
de telemetría V3 y detectar valores imposibles según parámetros estáticos.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from django.db.models import Max, Min, Avg, Count, Q
import pytz
from django.utils import timezone as django_timezone

from api.core.models import TelemetryRecord, CatchmentPoint, ProfileDataConfigCatchment, Variable
from api.telemetry.ingestion.controllers.flow import average_flow

logger = logging.getLogger(__name__)


def calculate_probable_flow_by_velocity(diameter_inches: float, velocity_mps: float) -> float:
    """
    Calcular caudal probable según diámetro y velocidad.
    """
    if not diameter_inches or diameter_inches <= 0 or not velocity_mps or velocity_mps <= 0:
        return 0.0
    
    try:
        diameter_m = float(diameter_inches) * 0.0254
        area = 3.14159 * ((diameter_m / 2) ** 2)
        q_m3s = area * float(velocity_mps)
        q_ls = q_m3s * 1000
        return round(q_ls, 2)
    except Exception:
        return 0.0


def calculate_max_flow_by_diameter(diameter_inches: float) -> float:
    """
    Calcular caudal máximo teórico según diámetro del flujómetro.
    """
    if not diameter_inches or diameter_inches <= 0:
        return 0.0
    
    try:
        diameter_m = float(diameter_inches) * 0.0254
        area = 3.14159 * ((diameter_m / 2) ** 2)
        v_max = 2.5
        q_max_m3s = area * v_max
        q_max_ls = q_max_m3s * 1000
        return q_max_ls * 1.2
    except Exception:
        return 0.0


def validate_flow_impossible(flow_value: float, diameter_inches: float) -> Tuple[bool, str]:
    """
    Validar si un valor de caudal es imposible según el diámetro.
    """
    if not diameter_inches or diameter_inches <= 0:
        return (False, "Sin diámetro configurado")
    
    max_flow = calculate_max_flow_by_diameter(diameter_inches)
    
    if max_flow <= 0:
        return (False, "No se puede calcular máximo")
    
    if flow_value > max_flow:
        return (True, f"Caudal {flow_value:.2f} L/s excede máximo teórico {max_flow:.2f} L/s")
    
    return (False, "OK")


def validate_level_impossible(level_value: float, d1: float, d3: float) -> Tuple[bool, str]:
    """
    Validar si un valor de nivel es imposible.
    """
    if not d1 or d1 <= 0:
        return (False, "Sin profundidad configurada")
    
    if level_value > d1:
        return (True, f"Nivel {level_value:.2f} m excede profundidad total {d1:.2f} m")
    
    if level_value < 0:
        return (True, f"Nivel negativo: {level_value:.2f} m")
    
    if d3 and d3 > 0:
        if level_value > (d3 + 5):
            return (True, f"Nivel {level_value:.2f} m muy por encima del sensor")
    
    return (False, "OK")


def analyze_data_coherence(point_catchment_id: int, days_back: int = 30) -> Dict:
    """
    Analizar coherencia de datos de telemetría para un punto de captación V3.
    """
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    end_date = now
    start_date = end_date - timedelta(days=days_back)
    
    try:
        point = CatchmentPoint.objects.select_related('project')\
            .prefetch_related('data_config_profiles', 'dga_data_config_profiles')\
            .get(id=point_catchment_id)
        profile = point.data_config_profiles.first()
        dga_config = point.dga_data_config_profiles.first()
    except CatchmentPoint.DoesNotExist:
        return {"error": "Punto no encontrado"}
    
    variables = list(Variable.objects.filter(point=point, is_active=True))
    
    has_totalizado = any(v.internal_code == "total" for v in variables)
    has_caudal = any(v.internal_code in ["flow", "caudal"] for v in variables)
    has_nivel = any(v.internal_code in ["nivel", "water_table"] for v in variables)
    
    records_qs = TelemetryRecord.objects.filter(
        point_id=point_catchment_id,
        timestamp__gte=start_date,
        timestamp__lte=end_date
    ).order_by('timestamp')
    
    records = list(records_qs)
    
    if not records:
        return {
            "error": "No hay datos en el período",
            "point_id": point_catchment_id,
            "point_name": str(point)
        }
    
    incidencias = []
    estadisticas = {}
    
    # Extraer valores de JSON data
    totals = [float(r.data.get('total', 0)) for r in records if r.data.get('total') is not None] if has_totalizado else []
    flows = [float(r.data.get('flow', r.data.get('caudal', 0))) for r in records]
    levels = [float(r.data.get('nivel', 0)) for r in records if r.data.get('nivel') is not None] if has_nivel else []
    total_diffs = [float(r.data.get('total_diff', 0)) for r in records] if has_totalizado else []
    
    if totals:
        estadisticas['total'] = {
            'min': min(totals),
            'max': max(totals),
            'promedio': sum(totals) / len(totals),
            'variacion': max(totals) - min(totals)
        }

    if flows:
        estadisticas['caudal'] = {
            'min': min(flows),
            'max': max(flows),
            'promedio': sum(flows) / len(flows)
        }
        if profile and profile.d5 and max(flows) > 0:
            is_impossible, msg = validate_flow_impossible(max(flows), float(profile.d5))
            if is_impossible:
                incidencias.append({'tipo': 'CRITICA', 'descripcion': 'Caudal imposible', 'detalle': msg})

    if levels:
        estadisticas['nivel'] = {
            'min': min(levels),
            'max': max(levels),
            'promedio': sum(levels) / len(levels)
        }
        if profile:
            is_impossible, msg = validate_level_impossible(max(levels), float(profile.d1 or 0), float(profile.d3 or 0))
            if is_impossible:
                incidencias.append({'tipo': 'CRITICA', 'descripcion': 'Nivel imposible', 'detalle': msg})

    # Telemetría del día
    today = end_date.date()
    today_recs = [r for r in records if r.timestamp.date() == today]
    count_today = len(today_recs)
    estadisticas['telemetria_dia'] = {
        'total_registros': count_today,
        'consumo_total': sum(float(r.data.get('total_diff', 0)) for r in today_recs),
    }

    return {
        'point_id': point_catchment_id,
        'point_name': str(point),
        'project': str(point.project) if point.project else None,
        'periodo': {'inicio': start_date.strftime('%Y-%m-%d'), 'fin': end_date.strftime('%Y-%m-%d'), 'dias': days_back},
        'variables': {'totalizado': has_totalizado, 'caudal': has_caudal, 'nivel': has_nivel},
        'estadisticas': estadisticas,
        'incidencias': incidencias,
        'total_registros': len(records),
        'incidencias_criticas': len([i for i in incidencias if i['tipo'] == 'CRITICA']),
        'incidencias_advertencia': len([i for i in incidencias if i['tipo'] == 'ADVERTENCIA']),
    }
