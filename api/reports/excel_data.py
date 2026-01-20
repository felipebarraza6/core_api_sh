"""
Funciones para obtener y procesar datos de BD (V3 Dinámico)
==========================================================

Funciones optimizadas para obtener datos de la base de datos V3
y calcular indicadores para los reportes Excel.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from django.db.models import Min, Max, Avg, Count, Sum, Q
import pytz

from api.telemetry.models import CatchmentPoint, TelemetryRecord, CoreVariable
from api.telemetry.processing import FormulaEngine

logger = logging.getLogger(__name__)


def get_point_variables(point: CatchmentPoint) -> Dict[str, bool]:
    """
    Obtener información de variables del punto de forma optimizada V3.
    """
    variables = CoreVariable.objects.filter(point=point, is_active=True)
    has_totalizado = variables.filter(internal_code="total").exists()
    has_caudal_promedio = variables.filter(internal_code__in=["flow", "caudal"]).exists()
    
    return {
        'has_totalizado': has_totalizado,
        'has_caudal_promedio': has_caudal_promedio,
        'pulses_factor': 1000  # Default en V3
    }


def get_months_with_data(point: CatchmentPoint, year_start: datetime, 
                         year_end: datetime) -> Dict[str, Dict]:
    """
    Obtener meses con datos usando agregación de BD (optimizado V3).
    """
    months_with_data = TelemetryRecord.objects.filter(
        point=point,
        timestamp__gte=year_start,
        timestamp__lte=year_end
    ).extra(
        select={'month': "TO_CHAR(timestamp, 'YYYY-MM')"}
    ).values('month').annotate(
        min_date=Min('timestamp'),
        max_date=Max('timestamp')
    ).order_by('month')
    
    months_data = {}
    for month_info in months_with_data:
        month_key = month_info['month']
        months_data[month_key] = {
            'start': month_info['min_date'],
            'end': month_info['max_date']
        }
    
    return months_data


def get_month_statistics(point: CatchmentPoint, month_start: datetime, 
                        month_end: datetime) -> Dict:
    """
    Obtener estadísticas del mes usando agregaciones de BD (optimizado V3).
    Nota: Las agregaciones en JSONField requieren sintaxis data__field.
    """
    return TelemetryRecord.objects.filter(
        point=point,
        timestamp__gte=month_start,
        timestamp__lte=month_end
    ).aggregate(
        total_registros=Count('id'),
        min_total=Min('data__total'),
        max_total=Max('data__total'),
        avg_nivel=Avg('data__nivel'),
        min_nivel=Min('data__nivel'),
        max_nivel=Max('data__nivel'),
        sum_total_diff=Sum('data__total_diff')
    )


def calculate_month_consumo(point: CatchmentPoint, month_start: datetime, 
                           month_end: datetime, has_totalizado: bool) -> float:
    """
    Calcular consumo total del mes de forma optimizada V3.
    """
    if not has_totalizado:
        month_stats = get_month_statistics(point, month_start, month_end)
        return float(month_stats.get('sum_total_diff') or 0.0)
    
    # Obtener primer y último registro
    primer_registro = TelemetryRecord.objects.filter(
        point=point,
        timestamp__gte=month_start,
        timestamp__lte=month_end
    ).order_by('timestamp').first()
    
    ultimo_registro = TelemetryRecord.objects.filter(
        point=point,
        timestamp__gte=month_start,
        timestamp__lte=month_end
    ).order_by('-timestamp').first()
    
    if primer_registro and ultimo_registro:
        try:
            primer_total = float(primer_registro.data.get('total', 0))
            ultimo_total = float(ultimo_registro.data.get('total', 0))
            if ultimo_total >= primer_total:
                return ultimo_total - primer_total
            else:
                return ultimo_total  # Reset
        except (ValueError, TypeError):
            pass
    
    month_stats = get_month_statistics(point, month_start, month_end)
    return float(month_stats.get('sum_total_diff') or 0.0)


def calculate_flow_optimized(record: TelemetryRecord, 
                            prev_record: Optional[TelemetryRecord],
                            has_caudal_promedio: bool, point_id: int) -> float:
    """
    Calcular flow de forma optimizada usando registro anterior en memoria V3.
    """
    data = record.data
    flow_val = float(data.get('flow', data.get('caudal', 0)))
    total_val = float(data.get('total', 0))
    total_diff = float(data.get('total_diff', 0))

    if not has_caudal_promedio or total_val <= 0 or total_diff <= 0:
        return flow_val
    
    if not prev_record:
        return flow_val
    
    try:
        chile_tz = pytz.timezone("America/Santiago")
        # En V3 usamos metadata para el timestamp del logger
        curr_ts = record.timestamp
        if record.metadata.get('last_logger_timestamp'):
             try:
                 curr_ts = datetime.fromisoformat(record.metadata['last_logger_timestamp'])
             except: pass
        
        if curr_ts.tzinfo is None:
            curr_ts = chile_tz.localize(curr_ts)
        
        prev_ts = prev_record.timestamp
        if prev_record.metadata.get('last_logger_timestamp'):
             try:
                 prev_ts = datetime.fromisoformat(prev_record.metadata['last_logger_timestamp'])
             except: pass

        if prev_ts.tzinfo is None:
            prev_ts = chile_tz.localize(prev_ts)
        
        time_diff = (curr_ts - prev_ts).total_seconds()
        if time_diff > 0:
            prev_total = float(prev_record.data.get('total', 0))
            total_delta = total_val - prev_total
            if total_delta > 0:
                flow_calculated = round((total_delta / time_diff) * 1000.0, 2)
                if abs(flow_calculated) < 1000:
                    return flow_calculated
    
    except Exception as e:
        logger.debug(f"Error calculando flow optimizado V3: {e}")
    
    return flow_val


def get_month_records_optimized(point: CatchmentPoint, month_start: datetime, 
                                month_end: datetime, max_records: int = 744) -> Tuple[List[TelemetryRecord], int]:
    """
    Obtener registros del mes filtrados por hora exacta V3.
    """
    month_records_detail = TelemetryRecord.objects.filter(
        point=point,
        timestamp__gte=month_start,
        timestamp__lte=month_end
    ).extra(
        where=["EXTRACT(MINUTE FROM timestamp) = 0 AND EXTRACT(SECOND FROM timestamp) = 0"]
    ).order_by('timestamp')
    
    total_records_month = TelemetryRecord.objects.filter(
        point=point,
        timestamp__gte=month_start,
        timestamp__lte=month_end
    ).count()
    
    month_records = list(month_records_detail[:max_records])
    
    return month_records, total_records_month


def get_month_flows_sample(point: CatchmentPoint, month_start: datetime, 
                           month_end: datetime, has_caudal_promedio: bool,
                           sample_size: int = 50) -> List[float]:
    """
    Obtener muestra de caudales del mes para calcular indicadores V3.
    """
    month_stats = get_month_statistics(point, month_start, month_end)
    total_records = month_stats.get('total_registros', 0)
    
    month_records_sample = TelemetryRecord.objects.filter(
        point=point,
        timestamp__gte=month_start,
        timestamp__lte=month_end
    ).order_by('timestamp')
    
    if total_records > sample_size:
        step = max(1, total_records // sample_size)
        month_records_sample = month_records_sample[::step][:sample_size]
    else:
        month_records_sample = list(month_records_sample)
    
    month_flows = []
    chile_tz = pytz.timezone("America/Santiago")
    
    for r in month_records_sample:
        data = r.data
        total_actual = float(data.get('total', 0))
        flow_val = float(data.get('flow', data.get('caudal', 0)))

        if has_caudal_promedio and total_actual > 0:
            try:
                point_dict = {"id": point.id}
                curr_ts = r.timestamp
                if r.metadata.get('last_logger_timestamp'):
                    try:
                        curr_ts = datetime.fromisoformat(r.metadata['last_logger_timestamp'])
                    except: pass
                
                if curr_ts.tzinfo is None:
                    curr_ts = chile_tz.localize(curr_ts)
                
                flow_calc = FormulaEngine.average_flow(point_dict, total_actual, curr_ts)
                if flow_calc > 0:
                    month_flows.append(flow_calc)
                    continue
            except:
                pass
        
        if flow_val > 0:
            month_flows.append(flow_val)
    
    # Fallback: usar agregación si no hay muestra
    if not month_flows:
        flow_stats = TelemetryRecord.objects.filter(
            point=point,
            timestamp__gte=month_start,
            timestamp__lte=month_end
        ).aggregate(
            avg_flow=Avg('data__flow')
        )
        if flow_stats.get('avg_flow'):
            month_flows = [float(flow_stats['avg_flow'])]
    
    return month_flows
