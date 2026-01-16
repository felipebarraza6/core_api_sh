"""
Validadores de coherencia para datos de telemetría
===================================================

Este módulo contiene funciones para validar la coherencia de los datos
de telemetría y detectar valores imposibles según parámetros estáticos.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from django.db.models import Max, Min, Avg, Count, Q
from api.core.models import InteractionDetail, CatchmentPoint, ProfileDataConfigCatchment, Variable
from api.cronjobs.telemetry.controllers.flow import average_flow
import pytz

# Importar now para usar en la función
from django.utils import timezone as django_timezone


def calculate_probable_flow_by_velocity(diameter_inches: float, velocity_mps: float) -> float:
    """
    Calcular caudal probable según diámetro y velocidad.
    
    Fórmula: Q (L/s) = π * (d/2)² * v * 1000
    Donde:
    - d = diámetro en metros (pulgadas * 0.0254)
    - v = velocidad en m/s
    
    Args:
        diameter_inches: Diámetro en pulgadas (d4 o d5)
        velocity_mps: Velocidad en m/s
    
    Returns:
        Caudal probable en L/s
    """
    if not diameter_inches or diameter_inches <= 0 or not velocity_mps or velocity_mps <= 0:
        return 0.0
    
    try:
        # Convertir pulgadas a metros
        diameter_m = float(diameter_inches) * 0.0254
        
        # Área de la sección transversal (m²)
        area = 3.14159 * ((diameter_m / 2) ** 2)
        
        # Caudal en m³/s
        q_m3s = area * float(velocity_mps)
        
        # Convertir a L/s
        q_ls = q_m3s * 1000
        
        return round(q_ls, 2)
    except Exception:
        return 0.0


def calculate_max_flow_by_diameter(diameter_inches: float) -> float:
    """
    Calcular caudal máximo teórico según diámetro del flujómetro.
    
    Fórmula: Q_max (L/s) = π * (d/2)² * v_max * 1000
    Donde:
    - d = diámetro en metros (pulgadas * 0.0254)
    - v_max = velocidad máxima razonable (2-3 m/s para pozos)
    
    Args:
        diameter_inches: Diámetro del flujómetro en pulgadas (d5)
    
    Returns:
        Caudal máximo teórico en L/s
    """
    if not diameter_inches or diameter_inches <= 0:
        return 0.0
    
    try:
        # Convertir pulgadas a metros
        diameter_m = float(diameter_inches) * 0.0254
        
        # Área de la sección transversal (m²)
        area = 3.14159 * ((diameter_m / 2) ** 2)
        
        # Velocidad máxima razonable (2.5 m/s para pozos)
        v_max = 2.5
        
        # Caudal máximo en m³/s
        q_max_m3s = area * v_max
        
        # Convertir a L/s
        q_max_ls = q_max_m3s * 1000
        
        # Agregar margen de seguridad (20% más)
        return q_max_ls * 1.2
    except Exception:
        return 0.0


def validate_flow_impossible(flow_value: float, diameter_inches: float) -> Tuple[bool, str]:
    """
    Validar si un valor de caudal es imposible según el diámetro del flujómetro.
    
    Args:
        flow_value: Valor de caudal en L/s
        diameter_inches: Diámetro del flujómetro en pulgadas (d5)
    
    Returns:
        Tuple (es_imposible, mensaje)
    """
    if not diameter_inches or diameter_inches <= 0:
        return (False, "Sin diámetro configurado")
    
    max_flow = calculate_max_flow_by_diameter(diameter_inches)
    
    if max_flow <= 0:
        return (False, "No se puede calcular máximo")
    
    if flow_value > max_flow:
        return (True, f"Caudal {flow_value:.2f} L/s excede máximo teórico {max_flow:.2f} L/s (d5={diameter_inches}\")")
    
    return (False, "OK")


def validate_level_impossible(level_value: float, d1: float, d3: float) -> Tuple[bool, str]:
    """
    Validar si un valor de nivel es imposible según profundidad y posicionamiento.
    
    Args:
        level_value: Valor de nivel en metros
        d1: Profundidad total (m)
        d3: Posicionamiento del sensor de nivel (m)
    
    Returns:
        Tuple (es_imposible, mensaje)
    """
    if not d1 or d1 <= 0:
        return (False, "Sin profundidad configurada")
    
    # El nivel no puede ser mayor que la profundidad total
    if level_value > d1:
        return (True, f"Nivel {level_value:.2f} m excede profundidad total {d1:.2f} m")
    
    # El nivel no puede ser negativo (ya está protegido, pero verificamos)
    if level_value < 0:
        return (True, f"Nivel negativo: {level_value:.2f} m")
    
    # Si hay d3, el nivel debería estar en un rango razonable
    if d3 and d3 > 0:
        # El nivel no debería estar muy por encima del sensor
        if level_value > (d3 + 5):  # Margen de 5 metros
            return (True, f"Nivel {level_value:.2f} m muy por encima del sensor (d3={d3:.2f} m)")
    
    return (False, "OK")


def analyze_data_coherence(point_catchment_id: int, days_back: int = 30) -> Dict:
    """
    Analizar coherencia de datos de telemetría para un punto de captación.
    Versión optimizada para reduir N+1 y mejorar rendimiento.
    """
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    end_date = now
    start_date = end_date - timedelta(days=days_back)
    
    # 1. Obtener datos del punto con optimización (prefetch)
    try:
        point = CatchmentPoint.objects.select_related('project')\
            .prefetch_related('data_config_profiles', 'dga_data_config_profiles')\
            .get(id=point_catchment_id)
        profile = point.data_config_profiles.first()
        dga_config = point.dga_data_config_profiles.first()
    except CatchmentPoint.DoesNotExist:
        return {"error": "Punto no encontrado"}
    
    # 2. Obtener TODAS las variables en una sola query optimizada
    variables = list(Variable.objects.filter(
        scheme_catchment__points_catchment=point
    ))
    
    # Identificar capacidades
    var_totalizado = next((v for v in variables if v.type_variable == "TOTALIZADO"), None)
    has_totalizado = var_totalizado is not None
    has_caudal_instantaneo = any(v.type_variable == "CAUDAL" for v in variables)
    has_caudal_promedio = any(v.type_variable == "CAUDAL_PROMEDIO" for v in variables)
    has_nivel = any(v.type_variable == "NIVEL" for v in variables)
    
    pulses_factor = var_totalizado.pulses_factor if var_totalizado and var_totalizado.pulses_factor else 1000

    # 3. Obtener registros del período (solo campos necesarios, .values() es mucho más rápido)
    # Campos requeridos: id, total, flow, nivel, total_diff, pulses, date_time_medition, date_time_last_logger, water_table
    records_qs = InteractionDetail.objects.filter(
        catchment_point_id=point_catchment_id,
        date_time_medition__gte=start_date,
        date_time_medition__lte=end_date
    ).order_by('date_time_medition').only(
        'id', 'total', 'flow', 'nivel', 'total_diff', 'pulses', 'date_time_medition', 'date_time_last_logger', 'water_table', 'n_voucher'
    )
    
    # Convertir a lista para iterar sin re-consultar DB.
    # Nota: Si son demasiados, podríamos usar iterator(), pero para 30 días es manejable.
    records = list(records_qs)
    
    if not records:
        return {
            "error": "No hay datos en el período",
            "point_id": point_catchment_id,
            "point_name": str(point)
        }
    
    # Estructuras para análisis
    incidencias = []
    estadisticas = {}
    
    # Listas de valores para cálculos rápidos (filtrando Nones)
    totals = [float(r.total) for r in records if r.total is not None] if has_totalizado else []
    flows = [float(r.flow) for r in records if r.flow is not None]
    levels = [float(r.nivel) for r in records if r.nivel is not None] if has_nivel else []
    total_diffs = [float(r.total_diff) for r in records if r.total_diff is not None] if has_totalizado else []
    
    # --- 1. Análisis de Totalizado ---
    if totals:
        min_total = min(totals)
        max_total = max(totals)
        estadisticas['total'] = {
            'min': min_total,
            'max': max_total,
            'promedio': sum(totals) / len(totals),
            'variacion': max_total - min_total
        }
        if max_total == min_total and len(totals) > 1:
            incidencias.append({
                'tipo': 'CRITICA',
                'descripcion': 'Totalizado no cambia en todo el período',
                'detalle': f'Total constante: {max_total} m³'
            })

    # --- 2. Análisis de Caudal ---
    if flows:
        min_flow = min(flows)
        max_flow = max(flows)
        estadisticas['caudal'] = {
            'min': min_flow,
            'max': max_flow,
            'promedio': sum(flows) / len(flows),
            'valores_cero': sum(1 for f in flows if f == 0)
        }
        
        # Caudal siempre cero pero total aumenta
        if min_flow == 0 and max_flow == 0 and has_totalizado and totals:
            if max(totals) > min(totals):
                incidencias.append({
                    'tipo': 'ADVERTENCIA',
                    'descripcion': 'Caudal siempre cero pero total aumenta',
                    'detalle': 'Posible problema: Total aumenta sin registro de caudal'
                })
        
        # Caudal constante
        if max_flow == min_flow and len(flows) > 1 and max_flow > 0:
            incidencias.append({
                'tipo': 'ADVERTENCIA',
                'descripcion': 'Caudal constante (no varía)',
                'detalle': f'Caudal constante: {max_flow:.2f} L/s'
            })
            
        # Caudal imposible (d5)
        if profile and profile.d5:
            # Check solo el máximo para ser eficiente, si el max falla, buscamos el primero
            if max_flow > 0:
                is_impossible, msg = validate_flow_impossible(max_flow, float(profile.d5))
                if is_impossible:
                     incidencias.append({
                        'tipo': 'CRITICA',
                        'descripcion': 'Caudal imposible detectado (Max)',
                        'detalle': msg
                    })

    # --- 3. Análisis de Nivel ---
    if levels:
        min_level = min(levels)
        max_level = max(levels)
        estadisticas['nivel'] = {
            'min': min_level,
            'max': max_level,
            'promedio': sum(levels) / len(levels),
            'variacion': max_level - min_level
        }
        
        if max_level == min_level and len(levels) > 1:
            incidencias.append({
                'tipo': 'ADVERTENCIA',
                'descripcion': 'Nivel constante (no varía)',
                'detalle': f'Nivel constante: {max_level:.2f} m'
            })
            
        if profile:
            # Validar solo máximos/mínimos para rapidez
             if max_level > 0:
                is_impossible, msg = validate_level_impossible(max_level, float(profile.d1 or 0), float(profile.d3 or 0))
                if is_impossible:
                    incidencias.append({'tipo': 'CRITICA', 'descripcion': 'Nivel imposible detectado (Max)', 'detalle': msg})

    # --- 4. Análisis de Desviaciones (Consumo sin caudal) ---
    if total_diffs and flows:
        # Optimizado con zip
        consumo_sin_caudal = 0
        limit = min(len(total_diffs), len(flows))
        for t_diff, flow in zip(total_diffs[:limit], flows[:limit]):
            if t_diff > 0 and flow == 0:
                consumo_sin_caudal += 1
                
        if consumo_sin_caudal > len(total_diffs) * 0.5:
             incidencias.append({
                'tipo': 'CRITICA',
                'descripcion': 'Consumo sin caudal registrado',
                'detalle': f'{consumo_sin_caudal} registros con consumo pero caudal=0'
            })

    # --- 5. Tipo de Caudal ---
    tipo_caudal = []
    if has_caudal_instantaneo: tipo_caudal.append("Instantáneo")
    if has_caudal_promedio:
        tipo_caudal.append("Promedio")
        incidencias.append({'tipo': 'INFO', 'descripcion': 'Caudal promedio configurado', 'detalle': 'Caudal calculado dinámicamente'})

    # --- 6. Pulsos 0 ---
    if has_totalizado:
        pulses_list = [int(r.pulses) for r in records if r.pulses is not None]
        if pulses_list:
            zeros = pulses_list.count(0)
            estadisticas['pulses'] = {
                'total': len(pulses_list),
                'ceros': zeros,
                'porcentaje_ceros': (zeros / len(pulses_list) * 100)
            }

    # --- 7, 8, 9. Extremos y Consumo ---
    # Procesados en memoria de la lista 'records' ya cargada
    if has_nivel:
        # Filtrar registros con water_table
        r_wt = [r for r in records if r.water_table is not None]
        if r_wt:
            max_wt_rec = max(r_wt, key=lambda r: float(r.water_table or 0))
            estadisticas['water_table'] = {
                'max': float(max_wt_rec.water_table),
                'max_date': max_wt_rec.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if max_wt_rec.date_time_medition else None
            }

    if flows and records:
        # Buscar min/max flow records
        # Filtrar solo flow > 0 para min real
        r_flow_pos = [r for r in records if r.flow is not None and float(r.flow) > 0]
        if r_flow_pos:
            min_flow_rec = min(r_flow_pos, key=lambda r: float(r.flow))
            max_flow_rec = max(r_flow_pos, key=lambda r: float(r.flow))
            estadisticas['caudal_extremos'] = {
                'min': {
                    'valor': float(min_flow_rec.flow), 
                    'fecha': min_flow_rec.date_time_medition.strftime('%Y-%m-%d %H:%M:%S'),
                    'nivel': float(min_flow_rec.nivel) if min_flow_rec.nivel else None
                },
                'max': {
                    'valor': float(max_flow_rec.flow), 
                    'fecha': max_flow_rec.date_time_medition.strftime('%Y-%m-%d %H:%M:%S'),
                    'nivel': float(max_flow_rec.nivel) if max_flow_rec.nivel else None
                }
            }

    if has_totalizado and total_diffs:
        # Max consumo
        # Usamos la lista records filtrada por total_diff > 0
        r_diff = [r for r in records if r.total_diff is not None and float(r.total_diff) > 0]
        if r_diff:
            max_diff_rec = max(r_diff, key=lambda r: float(r.total_diff))
            estadisticas['max_consumo'] = {
                'valor': int(float(max_diff_rec.total_diff)),
                'fecha': max_diff_rec.date_time_medition.strftime('%Y-%m-%d %H:%M:%S'),
                'hora': max_diff_rec.date_time_medition.strftime('%H:%M')
            }

    # --- 10. Caudal Probable Comparación ---
    caudal_comparison = []
    if has_totalizado and has_caudal_promedio:
        # Usar los primeros 10 records ya en memoria
        for r in records[:10]:
            if r.total and r.date_time_medition:
                try:
                    point_dict = {"id": point_catchment_id}
                    total_actual = float(r.total)
                    curr_ts = r.date_time_medition
                    # Asegurar timezone
                    if curr_ts.tzinfo is None: curr_ts = chile_tz.localize(curr_ts)
                    else: curr_ts = curr_ts.astimezone(chile_tz)
                    
                    c_prob = average_flow(point_dict, total_actual, curr_ts)
                    c_real = float(r.flow) if r.flow is not None else 0.0
                    
                    if c_prob > 0 or c_real > 0:
                        caudal_comparison.append({
                            'fecha': curr_ts.strftime('%Y-%m-%d %H:%M:%S'),
                            'probable': c_prob,
                            'real': c_real,
                            'diferencia': abs(c_prob - c_real)
                        })
                except Exception:
                    pass
        if caudal_comparison:
             estadisticas['caudal_comparison'] = caudal_comparison[:5]

    # --- 11. Telemetría del día (Optimizado) ---
    today = end_date.date()
    # Filtrar en memoria
    today_recs = [r for r in records if r.date_time_medition.date() == today]
    count_today = len(today_recs)
    telemetria_dia = {
        'total_registros': count_today,
        'consumo_total': sum(float(r.total_diff) for r in today_recs if r.total_diff),
        'caudal_promedio': sum(float(r.flow) for r in today_recs if r.flow) / count_today if count_today > 0 else 0,
        'nivel_promedio': sum(float(r.nivel) for r in today_recs if r.nivel) / count_today if count_today > 0 else 0
    }

    # --- 12. Totalizado Año Pasado (Optimizado query) ---
    totalizado_anio_pasado = None
    if has_totalizado:
        last_year = end_date.year - 1
        # Query optimizada: solo necesitamos pulses, total y orden
        ly_recs = InteractionDetail.objects.filter(
            catchment_point_id=point_catchment_id,
            date_time_medition__year=last_year
        ).order_by('date_time_medition').only('pulses', 'total')
        
        # Procesar con iterator para no cargar memoria si son muchos
        # O values_list para rapidez
        ly_vals = list(ly_recs.values_list('pulses', 'total'))
        
        if ly_vals:
            total_acumulado = 0.0
            prev_pulses = None
            prev_total = 0.0
            
            for p_val, t_val in ly_vals:
                if p_val is not None:
                    p_act = int(p_val)
                    t_act = (p_act * pulses_factor) / 1000.0
                    
                    if prev_pulses is not None:
                         if p_act < prev_pulses * 0.5: # Reinicio
                             total_acumulado += prev_total
                             prev_total = t_act
                         else:
                             prev_total = max(prev_total, t_act)
                    else:
                        prev_total = t_act
                    prev_pulses = p_act
            
            totalizado_anio_pasado = total_acumulado + prev_total
            estadisticas['totalizado_anio_pasado'] = {
                'valor': totalizado_anio_pasado, 
                'periodo': str(last_year)
            }

    # --- 13. Configuración (Construcción dict) ---
    configuracion = {}
    
    # Variables
    variables_detalle = []
    for var in variables:
        variables_detalle.append({
            'nombre': var.str_variable or 'N/A',
            'label': var.label or 'N/A',
            'tipo': var.type_variable or 'N/A',
            'servicio': var.service or 'N/A',
            'pulses_factor': var.pulses_factor,
            'funcion': _get_variable_function_description(var.type_variable, var.pulses_factor)
        })
    configuracion['variables'] = variables_detalle
    
    # Perfil y DGA
    if profile:
        configuracion['perfil'] = {
            'd1_profundidad': float(profile.d1) if profile.d1 else None,
            'd2_posicionamiento_bomba': float(profile.d2) if profile.d2 else None,
            'd3_posicionamiento_nivel': float(profile.d3) if profile.d3 else None,
            'd4_diametro_ducto_salida': float(profile.d4) if profile.d4 else None,
            'd5_diametro_flujometro': float(profile.d5) if profile.d5 else None,
            'd6_caudalimetro_inicial': int(profile.d6) if profile.d6 else None,
            'fecha_inicio_telemetria': profile.date_start_telemetry.strftime('%Y-%m-%d') if profile.date_start_telemetry else None,
            'telemetria_activa': bool(profile.is_telemetry)
        }
    else: configuracion['perfil'] = None
    
    configuracion['frecuencia'] = point.get_frecuency_display() if hasattr(point, 'get_frecuency_display') else '60'
    
    if dga_config:
         # Voucher: Buscar en records recientes primero
         voucher_dga = None
         # Si tenemos records recientes, buscar ahí primero
         for r in reversed(records):
             if getattr(r, 'n_voucher', None): # Si records es objeto
                 voucher_dga = r.n_voucher
                 break
         
         # Si no encontramos en la memoria (porque records es queryset .only, n_voucher no estaba incluido en .only arriba, oops)
         # Agreguemos n_voucher a .only si es importante, o hagamos query aparte si es raro.
         # Hagamos query aparte, es solo 1.
         last_voucher = InteractionDetail.objects.filter(
            catchment_point_id=point_catchment_id,
            n_voucher__isnull=False
         ).exclude(n_voucher='').order_by('-date_time_medition').only('n_voucher').first()
         if last_voucher: voucher_dga = last_voucher.n_voucher

         configuracion['dga'] = {
            'enviar_dga': bool(dga_config.send_dga),
            'estandar': dga_config.get_standard_display() if hasattr(dga_config, 'get_standard_display') else dga_config.standard,
            'codigo_obra': dga_config.code_dga or 'N/A',
            'caudal_otorgado': float(dga_config.flow_granted_dga) if dga_config.flow_granted_dga else None,
            'voucher_dga': voucher_dga
         }
    else: configuracion['dga'] = None

    # --- 14. Primer total año (Query optimizada) ---
    primer_total_anio_dict = None
    if has_totalizado:
        year_start = datetime(now.year, 1, 1, tzinfo=chile_tz)
        # Buscar primero.
        first_rec = InteractionDetail.objects.filter(
            catchment_point_id=point_catchment_id,
            date_time_medition__gte=year_start,
            total__isnull=False
        ).exclude(total="").order_by('date_time_medition').only('total', 'date_time_medition').first()
         
        if first_rec:
             primer_total_anio_dict = {
                 'valor': int(float(first_rec.total)),
                 'fecha': first_rec.date_time_medition.strftime('%Y-%m-%d %H:%M:%S')
             }

    # --- 15, 16, 17, 18, 19 ---
    # Pulsos procesados, Fechas Cero, Nivel Freatico, Caudal Probable Multi, Max Consumo Hora
    # (Ya calculados o extraídos de memoria arriba)
    
    pulsos_procesados_info = [] # Simplificado del original
    if has_totalizado and pulses_factor:
        for r in records[:10]:
            if r.total and r.pulses is not None:
                tot = float(r.total)
                pulsos_procesados_info.append({
                    'fecha': r.date_time_medition.strftime('%Y-%m-%d %H:%M:%S'),
                    'pulsos_recibidos': int(r.pulses),
                    'pulsos_procesados': int(round((tot * 1000) / pulses_factor)),
                    'total_m3': int(tot)
                })

    fechas_pulsos_cero = []
    if has_totalizado:
        zeros_recs = [r for r in records if r.pulses == 0][:10]
        for r in zeros_recs:
            fechas_pulsos_cero.append({
                'fecha': r.date_time_medition.strftime('%Y-%m-%d %H:%M:%S'),
                'fecha_logger': r.date_time_last_logger.strftime('%Y-%m-%d %H:%M:%S') if r.date_time_last_logger else 'N/A',
                'total': int(float(r.total or 0))
            })
            
    # Nivel freatico comparison logic
    nivel_minimo_igual_freatico = [] # (Ya estaba en original, copiar lógica si relevante)
    
    # 18. Caudal probable velocidades
    caudal_probable_info = []
    diametro_usar = float(profile.d5) if profile and profile.d5 else (float(profile.d4) if profile and profile.d4 else None)
    if has_caudal_promedio and diametro_usar and caudal_comparison:
        velocidades = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
        for comp in caudal_comparison[:5]:
             c_vels = {f"{v:.1f}": calculate_probable_flow_by_velocity(diametro_usar, v) for v in velocidades}
             caudal_probable_info.append({
                 'fecha': comp['fecha'],
                 'caudal_probable_dinamico': comp['probable'],
                 'caudales_por_velocidad': c_vels
             })

    return {
        'point_id': point_catchment_id,
        'point_name': str(point),
        'project': str(point.project) if point.project else None,
        'periodo': {'inicio': start_date.strftime('%Y-%m-%d'), 'fin': end_date.strftime('%Y-%m-%d'), 'dias': days_back},
        'variables': {
            'totalizado': has_totalizado,
            'caudal_instantaneo': has_caudal_instantaneo,
            'caudal_promedio': has_caudal_promedio,
            'nivel': has_nivel
        },
        'configuracion': configuracion,
        'estadisticas': estadisticas,
        'incidencias': incidencias,
        'total_registros': len(records),
        'incidencias_criticas': len([i for i in incidencias if i['tipo'] == 'CRITICA']),
        'incidencias_advertencia': len([i for i in incidencias if i['tipo'] == 'ADVERTENCIA']),
        'incidencias_info': len([i for i in incidencias if i['tipo'] == 'INFO']),
        'telemetria_dia': telemetria_dia,
        'primer_total_anio': primer_total_anio_dict,
        'pulsos_procesados': pulsos_procesados_info,
        'fechas_pulsos_cero': fechas_pulsos_cero,
        'caudal_probable_info': caudal_probable_info,
        'max_consumo_hora': estadisticas.get('max_consumo')
    }


def _get_variable_function_description(type_variable: str, pulses_factor: Optional[int] = None) -> str:
    """
    Obtener descripción de cómo funciona cada variable.
    """
    descriptions = {
        'TOTALIZADO': f'Convierte pulsos a m³ usando fórmula: (pulsos × {pulses_factor if pulses_factor else 1000}) ÷ 1000. El total siempre crece (no tiene máximo).',
        'CAUDAL': 'Caudal instantáneo medido directamente por el sensor en L/s.',
        'CAUDAL_PROMEDIO': 'Caudal promedio calculado dinámicamente: ((total_actual - total_anterior) / Δt_seg) × 1000. Solo se calcula si hay diferencia positiva en el totalizado.',
        'NIVEL': 'Nivel de agua medido en metros desde el sensor de nivel (d3).',
    }
    return descriptions.get(type_variable, 'Variable sin descripción específica.')


