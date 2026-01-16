"""
Utilidades para cálculo histórico de veracidad.

IMPORTANTE: Esta funcionalidad es NUEVA y no modifica el cálculo actual.
El cálculo actual sigue funcionando igual si no se proporciona período.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pytz
from django.utils import timezone

from django.db.models import Q, Count, Avg
from api.core.models import (
    InteractionDetail,
    CatchmentPoint,
    DgaDataConfigCatchment,
    ProfileDataConfigCatchment,
    Variable
)
from api.core.validators.telemetry_validator import calculate_probable_flow_by_velocity


def calculate_historical_veracidad(
    obras_points_list: List[CatchmentPoint],
    period_days: int = 90,  # Por defecto: último trimestre (90 días)
    project_filter: Optional[Q] = None,
    point_filter: Optional[Q] = None
) -> Dict:
    """
    Calcula veracidad histórica analizando registros de un período.
    
    Args:
        obras_points_list: Lista de puntos con código de obra
        period_days: Días hacia atrás para analizar (default: 90 = trimestre)
        project_filter: Filtro opcional por proyecto
        point_filter: Filtro opcional por punto
        
    Returns:
        Dict con estadísticas de veracidad histórica
    """
    chile_tz = pytz.timezone("America/Santiago")
    now = timezone.now()
    period_start = now - timedelta(days=period_days)
    
    # Estadísticas
    points_with_flow = 0
    points_with_d5 = 0
    points_flow_above_probable_count = 0
    veracidad_dict = {}
    
    # Para cada punto, analizar registros del período
    for point in obras_points_list:
        profile = point.data_config_profiles.first()
        if not profile or not profile.is_telemetry:
            continue
        
        # Verificar variables
        variables = Variable.objects.filter(
            scheme_catchment__points_catchment=point
        ).distinct()
        variable_types = [v.type_variable for v in variables if v.type_variable]
        has_caudal = any(t in variable_types for t in ["CAUDAL", "CAUDAL_PROMEDIO"])
        
        if not has_caudal:
            continue
        
        # Este punto tiene código de obra, telemetría activa y CAUDAL/CAUDAL_PROMEDIO
        points_with_flow += 1
        
        # Verificar si tiene d5
        diametro = None
        if profile.d5 and float(profile.d5) > 0:
            diametro = float(profile.d5)
            points_with_d5 += 1
        
        if not diametro:
            continue
        
        # Obtener registros del período para este punto
        records_qs = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=period_start,
            date_time_medition__lte=now
        ).order_by('date_time_medition')
        
        if not records_qs.exists():
            continue
        
        # Analizar cada registro del período
        records_above_probable = 0
        total_records_analyzed = 0
        all_excesos_records = []  # Guardar TODOS los registros con exceso
        
        for record in records_qs:
            # Calcular flow dinámicamente si corresponde
            flow_value = record.flow or 0.0
            has_caudal_promedio = "CAUDAL_PROMEDIO" in variable_types
            
            if has_caudal_promedio and profile.d6 and float(profile.d6) > 0:
                try:
                    from api.core.serializers.interaction_detail import InteractionDetailModelSerializer
                    serializer = InteractionDetailModelSerializer(record)
                    serialized_data = serializer.data
                    flow_value = serialized_data.get('flow', 0.0)
                except Exception:
                    flow_value = record.flow or 0.0
            
            if flow_value and float(flow_value) > 0:
                total_records_analyzed += 1
                # Calcular caudal probable
                caudal_probable = calculate_probable_flow_by_velocity(diametro, 2.5)
                
                if float(flow_value) > caudal_probable:
                    records_above_probable += 1
                    exceso = float(flow_value) - caudal_probable
                    
                    # Guardar TODOS los registros con exceso (no solo el máximo)
                    all_excesos_records.append({
                        'record_id': record.id,
                        'date_time': record.date_time_medition,
                        'flow': float(flow_value),
                        'caudal_probable': caudal_probable,
                        'exceso': exceso,
                        'pct_exceso': (exceso / caudal_probable * 100) if caudal_probable > 0 else 0,
                        'pulses': record.pulses or 0
                    })
        
        # Calcular % de tiempo que excede el probable
        pct_time_above_probable = (
            (records_above_probable / total_records_analyzed * 100)
            if total_records_analyzed > 0 else 0
        )
        
        # Si hay registros con exceso, agregar TODOS a la lista
        if all_excesos_records:
            points_flow_above_probable_count += 1
            
            # Agregar a diccionario de veracidad - UN REGISTRO POR CADA EXCESO
            dga_profile = point.dga_data_config_profiles.first()
            codigo_obra = dga_profile.code_dga if dga_profile and dga_profile.code_dga else None
            
            # Crear una entrada por cada registro con exceso
            for exceso_record in all_excesos_records:
                # Usar un ID único combinando point_id y record_id
                unique_key = f"{point.id}_{exceso_record['record_id']}"
                
                fecha = exceso_record['date_time']
                horario = fecha.strftime('%d/%m/%Y %H:%M') if fecha else None
                caudal_medido = exceso_record['flow']
                caudal_probable = exceso_record['caudal_probable']
                exceso = exceso_record['exceso']
                pct_exceso = exceso_record['pct_exceso']
                
                veracidad_dict[unique_key] = {
                    'nombre': point.title,
                    'punto': point.title,
                    'proyecto': point.project.name if point.project else "Sin proyecto",
                    'codigo_obra': codigo_obra,
                    'pct_time_above_probable': round(pct_time_above_probable, 1),
                    'records_above_probable': records_above_probable,
                    'total_records_analyzed': total_records_analyzed,
                    'priority': 2,
                    'tipo_error': 'Exceso Caudal Histórico',
                    # Campos adicionales para la tabla
                    'fecha': fecha,
                    'horario': horario,
                    'pulses': exceso_record['pulses'],
                    'variables': variable_types if variable_types else [],
                    'caudal_medido': round(caudal_medido, 2) if caudal_medido else None,
                    'caudal_real': round(caudal_medido, 2) if caudal_medido else None,
                    'caudal_probable': round(caudal_probable, 2) if caudal_probable else None,
                    'exceso': round(exceso, 2) if exceso else None,
                    'pct_exceso': round(pct_exceso, 1) if pct_exceso else None,
                    'nivel': None,
                    'point_id': point.id,
                    'record_id': exceso_record['record_id']
                }
    
    # Calcular % de veracidad histórica
    pct_veracidad = (
        ((points_with_d5 - points_flow_above_probable_count) / points_with_d5 * 100)
        if points_with_d5 > 0 else 0
    )
    
    return {
        'pct_veracidad': round(pct_veracidad, 1),
        'pct_veracidad_count': points_with_d5 - points_flow_above_probable_count,
        'pct_veracidad_total': points_with_flow,
        'pct_veracidad_con_d5': points_with_d5,
        'pct_veracidad_pasan_probable': points_flow_above_probable_count,
        'veracidad_lista': list(veracidad_dict.values()),
        'period_days': period_days,
        'period_start': period_start.isoformat(),
        'period_end': now.isoformat()
    }

