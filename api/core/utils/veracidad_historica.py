"""
Utilidades para cálculo histórico de veracidad (V3 Dinámico).
Calcula veracidad analizando registros de un período usando esquema V3.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pytz
from django.utils import timezone
from django.db.models import Q, Count, Avg

from api.telemetry.models.telemetry import (
    TelemetryRecord,
    CoreVariable
)
from api.telemetry.models.catchment_points import (
    CatchmentPoint,
    ProfileDataConfigCatchment
)
from api.telemetry.validators.telemetry_validator import calculate_probable_flow_by_velocity


def calculate_historical_veracidad(
    obras_points_list: List[CatchmentPoint],
    period_days: int = 90,
    project_filter: Optional[Q] = None,
    point_filter: Optional[Q] = None
) -> Dict:
    """
    Calcula veracidad histórica analizando registros V3 de un período.
    """
    now = timezone.now()
    period_start = now - timedelta(days=period_days)
    
    points_with_flow = 0
    points_with_d5 = 0
    points_flow_above_probable_count = 0
    veracidad_dict = {}
    
    for point in obras_points_list:
        profile = point.data_config_profiles.first()
        if not profile or not profile.is_telemetry:
            continue
        
        variables = CoreVariable.objects.filter(point=point, is_active=True)
        variable_codes = list(variables.values_list('internal_code', flat=True))
        has_caudal = any(c in variable_codes for c in ["flow", "caudal"])
        
        if not has_caudal:
            continue
        
        points_with_flow += 1
        diametro = float(profile.d5) if profile.d5 and float(profile.d5) > 0 else None
        if diametro:
            points_with_d5 += 1
        else:
            continue
        
        records_qs = TelemetryRecord.objects.filter(
            point=point,
            timestamp__gte=period_start,
            timestamp__lte=now
        ).order_by('timestamp')
        
        if not records_qs.exists():
            continue
        
        records_above_probable = 0
        total_records_analyzed = 0
        all_excesos_records = []
        
        for record in records_qs:
            data = record.data
            flow_value = float(data.get('flow', data.get('caudal', 0)))
            
            if flow_value > 0:
                total_records_analyzed += 1
                caudal_probable = calculate_probable_flow_by_velocity(diametro, 2.5)
                
                if flow_value > caudal_probable:
                    records_above_probable += 1
                    exceso = flow_value - caudal_probable
                    all_excesos_records.append({
                        'record_id': record.id,
                        'date_time': record.timestamp,
                        'flow': flow_value,
                        'caudal_probable': caudal_probable,
                        'exceso': exceso,
                        'pct_exceso': (exceso / caudal_probable * 100) if caudal_probable > 0 else 0,
                        'pulses': data.get('pulses', 0)
                    })
        
        pct_time_above_probable = (records_above_probable / total_records_analyzed * 100) if total_records_analyzed > 0 else 0
        
        if all_excesos_records:
            points_flow_above_probable_count += 1
            from api.compliance.models import PointComplianceConfig
            compliance_config = PointComplianceConfig.objects.filter(
                point=point, provider__name="dga", is_active=True
            ).first()
            codigo_obra = compliance_config.config_data.get('code_dga') if compliance_config else None
            
            for exceso_record in all_excesos_records:
                unique_key = f"{point.id}_{exceso_record['record_id']}"
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
                    'fecha': exceso_record['date_time'],
                    'horario': exceso_record['date_time'].strftime('%d/%m/%Y %H:%M'),
                    'pulses': exceso_record['pulses'],
                    'caudal_medido': round(exceso_record['flow'], 2),
                    'caudal_real': round(exceso_record['flow'], 2),
                    'caudal_probable': round(exceso_record['caudal_probable'], 2),
                    'exceso': round(exceso_record['exceso'], 2),
                    'pct_exceso': round(exceso_record['pct_exceso'], 1),
                    'point_id': point.id,
                    'record_id': exceso_record['record_id']
                }
    
    pct_veracidad = ((points_with_d5 - points_flow_above_probable_count) / points_with_d5 * 100) if points_with_d5 > 0 else 0
    
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
