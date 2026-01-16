"""
Funciones para obtener y procesar datos de BD
==============================================

Funciones optimizadas para obtener datos de la base de datos
y calcular indicadores para los reportes Excel.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from django.db.models import Min, Max, Avg, Count, Sum
import pytz

from api.core.models import CatchmentPoint, InteractionDetail, Variable
from api.core.validators.telemetry_validator import analyze_data_coherence
from api.cronjobs.telemetry.controllers.flow import average_flow


def get_point_variables(point: CatchmentPoint) -> Dict[str, bool]:
    """
    Obtener información de variables del punto de forma optimizada.
    
    Args:
        point: CatchmentPoint
        
    Returns:
        dict: Diccionario con has_totalizado, has_caudal_promedio, pulses_factor
    """
    variables = Variable.objects.filter(scheme_catchment__points_catchment=point)
    has_totalizado = variables.filter(type_variable="TOTALIZADO").exists()
    has_caudal_promedio = variables.filter(type_variable="CAUDAL_PROMEDIO").exists()
    var_totalizado = variables.filter(type_variable="TOTALIZADO").first()
    pulses_factor = var_totalizado.pulses_factor if var_totalizado and var_totalizado.pulses_factor else 1000
    
    return {
        'has_totalizado': has_totalizado,
        'has_caudal_promedio': has_caudal_promedio,
        'pulses_factor': pulses_factor
    }


def get_months_with_data(point: CatchmentPoint, year_start: datetime, 
                         year_end: datetime) -> Dict[str, Dict]:
    """
    Obtener meses con datos usando agregación de BD (optimizado).
    
    Args:
        point: CatchmentPoint
        year_start: Fecha de inicio del año
        year_end: Fecha de fin del año
        
    Returns:
        dict: Diccionario con meses como clave y {start, end} como valor
    """
    months_with_data = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=year_start,
        date_time_medition__lte=year_end
    ).extra(
        select={'month': "TO_CHAR(date_time_medition, 'YYYY-MM')"}
    ).values('month').annotate(
        min_date=Min('date_time_medition'),
        max_date=Max('date_time_medition')
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
    Obtener estadísticas del mes usando agregaciones de BD (optimizado).
    
    Args:
        point: CatchmentPoint
        month_start: Fecha de inicio del mes
        month_end: Fecha de fin del mes
        
    Returns:
        dict: Estadísticas agregadas del mes
    """
    return InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=month_start,
        date_time_medition__lte=month_end
    ).aggregate(
        total_registros=Count('id'),
        min_total=Min('total'),
        max_total=Max('total'),
        avg_nivel=Avg('nivel'),
        min_nivel=Min('nivel'),
        max_nivel=Max('nivel'),
        sum_total_diff=Sum('total_diff')
    )


def calculate_month_consumo(point: CatchmentPoint, month_start: datetime, 
                           month_end: datetime, has_totalizado: bool) -> float:
    """
    Calcular consumo total del mes de forma optimizada.
    
    Args:
        point: CatchmentPoint
        month_start: Fecha de inicio del mes
        month_end: Fecha de fin del mes
        has_totalizado: Si tiene variable TOTALIZADO
        
    Returns:
        float: Consumo total del mes en m³
    """
    if not has_totalizado:
        # Si no hay totalizado, sumar total_diff
        month_stats = get_month_statistics(point, month_start, month_end)
        return month_stats.get('sum_total_diff') or 0.0
    
    # Obtener primer y último registro
    primer_registro = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=month_start,
        date_time_medition__lte=month_end
    ).order_by('date_time_medition').first()
    
    ultimo_registro = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=month_start,
        date_time_medition__lte=month_end
    ).order_by('-date_time_medition').first()
    
    if primer_registro and ultimo_registro and primer_registro.total and ultimo_registro.total:
        try:
            primer_total = float(primer_registro.total)
            ultimo_total = float(ultimo_registro.total)
            if ultimo_total >= primer_total:
                return ultimo_total - primer_total
            else:
                return ultimo_total  # Reset
        except:
            pass
    
    # Fallback: usar sum_total_diff
    month_stats = get_month_statistics(point, month_start, month_end)
    return month_stats.get('sum_total_diff') or 0.0


def calculate_flow_optimized(record: InteractionDetail, prev_record: Optional[InteractionDetail],
                            has_caudal_promedio: bool, point_id: int) -> float:
    """
    Calcular flow de forma optimizada usando registro anterior en memoria.
    
    Args:
        record: Registro actual
        prev_record: Registro anterior (ya en memoria)
        has_caudal_promedio: Si tiene variable CAUDAL_PROMEDIO
        point_id: ID del punto
        
    Returns:
        float: Valor de flow calculado
    """
    if not has_caudal_promedio or not record.total or not record.total_diff or record.total_diff <= 0:
        return float(record.flow) if record.flow else 0.0
    
    if not prev_record or not prev_record.total:
        return float(record.flow) if record.flow else 0.0
    
    try:
        chile_tz = pytz.timezone("America/Santiago")
        curr_ts = record.date_time_last_logger if record.date_time_last_logger else record.date_time_medition
        if not curr_ts:
            return float(record.flow) if record.flow else 0.0
        
        if curr_ts.tzinfo is None:
            curr_ts = chile_tz.localize(curr_ts)
        else:
            curr_ts = curr_ts.astimezone(chile_tz)
        
        prev_ts_to_use = prev_record.date_time_last_logger if prev_record.date_time_last_logger else prev_record.date_time_medition
        if not prev_ts_to_use:
            return float(record.flow) if record.flow else 0.0
        
        if prev_ts_to_use.tzinfo is None:
            prev_ts_to_use = chile_tz.localize(prev_ts_to_use)
        else:
            prev_ts_to_use = prev_ts_to_use.astimezone(chile_tz)
        
        time_diff = (curr_ts - prev_ts_to_use).total_seconds()
        if time_diff > 0:
            total_diff = float(record.total) - float(prev_record.total)
            if total_diff > 0:
                flow_value = round((total_diff / time_diff) * 1000.0, 2)
                if abs(flow_value) < 1000:
                    return flow_value
    
    except Exception:
        pass
    
    return float(record.flow) if record.flow else 0.0


def get_month_records_optimized(point: CatchmentPoint, month_start: datetime, 
                                month_end: datetime, max_records: int = 744) -> Tuple[List[InteractionDetail], int]:
    """
    Obtener registros del mes filtrados por hora exacta (00:00, 01:00, 02:00, etc.).
    
    ⚠️ OPTIMIZACIÓN: Filtra solo registros con hora exacta (:00:00) en date_time_medition.
    Máximo 744 registros (24 horas/día × 31 días máximo).
    
    Args:
        point: CatchmentPoint
        month_start: Fecha de inicio del mes
        month_end: Fecha de fin del mes
        max_records: Máximo de registros a retornar (default: 744 = 24h × 31 días)
        
    Returns:
        tuple: (lista de registros filtrados por hora, total de registros en el mes sin filtrar)
    """
    # ✅ OPTIMIZACIÓN: Filtrar solo registros con hora exacta (:00:00) en date_time_medition
    # Usar extra() para filtrar por hora exacta usando EXTRACT o TO_CHAR
    month_records_detail = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=month_start,
        date_time_medition__lte=month_end
    ).extra(
        where=["EXTRACT(MINUTE FROM date_time_medition) = 0 AND EXTRACT(SECOND FROM date_time_medition) = 0"]
    ).order_by('date_time_medition')
    
    # Contar total de registros del mes (sin filtrar) para mostrar en la nota
    total_records_month = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=month_start,
        date_time_medition__lte=month_end
    ).count()
    
    # Limitar a máximo 744 registros (24 horas × 31 días)
    month_records = list(month_records_detail[:max_records])
    
    return month_records, total_records_month


def get_month_flows_sample(point: CatchmentPoint, month_start: datetime, 
                           month_end: datetime, has_caudal_promedio: bool,
                           sample_size: int = 50) -> List[float]:
    """
    Obtener muestra de caudales del mes para calcular indicadores (optimizado).
    
    Args:
        point: CatchmentPoint
        month_start: Fecha de inicio del mes
        month_end: Fecha de fin del mes
        has_caudal_promedio: Si tiene variable CAUDAL_PROMEDIO
        sample_size: Tamaño de la muestra
        
    Returns:
        list: Lista de valores de caudal
    """
    month_stats = get_month_statistics(point, month_start, month_end)
    total_records = month_stats.get('total_registros', 0)
    
    month_records_sample = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=month_start,
        date_time_medition__lte=month_end
    ).order_by('date_time_medition')
    
    if total_records > sample_size:
        step = max(1, total_records // sample_size)
        month_records_sample = month_records_sample[::step][:sample_size]
    else:
        month_records_sample = list(month_records_sample)
    
    month_flows = []
    chile_tz = pytz.timezone("America/Santiago")
    
    for r in month_records_sample:
        if has_caudal_promedio and r.total:
            try:
                point_dict = {"id": point.id}
                total_actual = float(r.total)
                curr_ts = r.date_time_last_logger if r.date_time_last_logger else r.date_time_medition
                if curr_ts:
                    if curr_ts.tzinfo is None:
                        curr_ts = chile_tz.localize(curr_ts)
                    else:
                        curr_ts = curr_ts.astimezone(chile_tz)
                    flow_calc = average_flow(point_dict, total_actual, curr_ts)
                    if flow_calc > 0:
                        month_flows.append(flow_calc)
            except:
                pass
        elif r.flow:
            month_flows.append(float(r.flow))
    
    # Si no hay caudales calculados, usar agregación de BD
    if not month_flows:
        flow_stats = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=month_start,
            date_time_medition__lte=month_end,
            flow__gt=0
        ).aggregate(
            avg_flow=Avg('flow'),
            max_flow=Max('flow'),
            min_flow=Min('flow')
        )
        if flow_stats.get('avg_flow'):
            month_flows = [flow_stats['avg_flow']]
    
    return month_flows

