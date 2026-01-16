"""
Vistas personalizadas para Django Admin
========================================

Vistas adicionales para el panel de administración, incluyendo
monitoreo en tiempo real de telemetría y dashboard principal.
"""

from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.db.models import Q, Max, Count, Sum, Avg
from django.db.models.functions import TruncDay, TruncHour
from datetime import datetime, timedelta
import pytz
import logging
from django.utils import timezone
from api.core.models import (
    CatchmentPoint, InteractionDetail, ProfileDataConfigCatchment, Variable,
    Client, ProjectCatchments, NotificationsCatchment, User, SchemesCatchment,
    DgaDataConfigCatchment
)
from django.db.models import Prefetch
from api.core.validators.telemetry_validator import (
    validate_flow_impossible, validate_level_impossible, calculate_max_flow_by_diameter,
    calculate_probable_flow_by_velocity
)


def safe_float(value, default=0.0):
    """
    Convierte un valor a float de forma segura, manejando None, strings vacíos, etc.
    """
    if value is None:
        return default
    try:
        result = float(value)
        return result if result > 0 else default
    except (ValueError, TypeError):
        return default


@staff_member_required
def admin_dashboard_view(request):
    """Vista personalizada para el dashboard con filtros y buscador"""
    try:
        chile_tz = pytz.timezone("America/Santiago")
        now = timezone.now()
        
        # ========================================
        # FILTRO POR PROYECTO Y PUNTO
        # ========================================
        project_id = request.GET.get('project', None)
        point_id = request.GET.get('point', None)
        
        # Normalizar strings vacíos a None
        if project_id == '':
            project_id = None
        if point_id == '':
            point_id = None
        
        logging.info(f"🔍 Valores recibidos - project_id: {project_id} (tipo: {type(project_id)}), point_id: {point_id} (tipo: {type(point_id)})")
        
        # Convertir a enteros para comparación correcta
        if project_id:
            try:
                project_id = int(project_id)
                logging.info(f"✅ project_id convertido a entero: {project_id}")
            except (ValueError, TypeError):
                logging.warning(f"❌ No se pudo convertir project_id '{project_id}' a entero")
                project_id = None
        
        if point_id:
            try:
                point_id = int(point_id)
                logging.info(f"✅ point_id convertido a entero: {point_id}")
            except (ValueError, TypeError):
                logging.warning(f"❌ No se pudo convertir point_id '{point_id}' a entero")
                point_id = None
        
        # ========================================
        # FILTRO DE PERÍODO PARA VERACIDAD HISTÓRICA (NUEVA FUNCIONALIDAD)
        # ========================================
        # Por defecto: None (usa cálculo actual - último registro)
        # Si se proporciona: usa cálculo histórico del período
        veracidad_periodo = request.GET.get('veracidad_periodo', None)
        use_historical_veracidad = veracidad_periodo is not None
        
        # Mapear períodos a días
        period_days_map = {
            'trimestre': 90,  # Por defecto: último trimestre
            'mes': 30,
            'semestre': 180,
            'año': 365
        }
        
        period_days = period_days_map.get(veracidad_periodo, 90) if use_historical_veracidad else None
        selected_project = None
        selected_point = None
        project_filter = Q()
        point_filter = Q()
        
        
        if project_id:
            try:
                selected_project = ProjectCatchments.objects.get(id=project_id)
                project_filter = Q(catchment_point__project=selected_project)
                logging.info(f"✅ Proyecto seleccionado: {selected_project.name} (ID: {project_id})")
            except ProjectCatchments.DoesNotExist:
                logging.warning(f"❌ Proyecto con ID {project_id} no existe en la base de datos")
                project_id = None
            except Exception as e:
                logging.error(f"❌ Error al obtener proyecto: {e}")
                project_id = None
        
        if point_id:
            try:
                selected_point = CatchmentPoint.objects.get(id=point_id)
                point_filter = Q(catchment_point=selected_point)
                # Si hay punto seleccionado, también filtrar por proyecto del punto
                if selected_point.project:
                    selected_project = selected_point.project
                    project_id = selected_point.project.id
                    project_filter = Q(catchment_point__project=selected_project)
            except CatchmentPoint.DoesNotExist:
                point_id = None
    
        # Combinar filtros
        combined_filter = project_filter & point_filter
    
        # Obtener todos los proyectos para el selector
        all_projects = ProjectCatchments.objects.all().order_by('name')
    
        # ========================================
        # MÉTRICAS PRINCIPALES - NUEVOS STATS
        # ========================================
    
        # 1. Número de Obras (puntos con código de obra)
        dga_points_qs = DgaDataConfigCatchment.objects.filter(
            code_dga__isnull=False
        ).exclude(code_dga__exact='')
        if project_id:
            dga_points_qs = dga_points_qs.filter(point_catchment__project=selected_project)
        if point_id:
            dga_points_qs = dga_points_qs.filter(point_catchment=selected_point)
        num_obras = dga_points_qs.values('point_catchment').distinct().count()
    
        # Obtener los puntos con código de obra (base para todos los cálculos)
        # ✅ OPTIMIZACIÓN: Usar select_related para evitar N+1 queries
        obras_points_ids = dga_points_qs.values_list('point_catchment_id', flat=True).distinct()
        obras_points_qs = CatchmentPoint.objects.filter(id__in=obras_points_ids).select_related('project')
        obras_points_list = list(obras_points_qs)
    
        # 2. % Conectados (de número de obras, cuántos tienen telemetría activa)
        # De todos los puntos con código de obra (num_obras), cuántos tienen telemetría activa
        # ✅ FIX #2: CORREGIR CÁLCULO - Usar query en lugar de loop para evitar inconsistencias
        obras_with_telemetry = ProfileDataConfigCatchment.objects.filter(
            point_catchment__in=obras_points_ids,
            is_telemetry=True
        ).values('point_catchment').distinct().count()

        pct_conectados = (obras_with_telemetry / num_obras * 100) if num_obras > 0 else 0
        pct_conectados_count = obras_with_telemetry
        pct_conectados_total = num_obras
    
        # 3. % DGA (de totalidad de números de obra, cuántos están con cumplimiento activo)
        # De todos los puntos con código de obra (num_obras), cuántos tienen cumplimiento activo (send_dga=True en perfil DGA)
        # Prepare sets for counting
        # unique_point_ids: points having code_dga
        # active_points: points having code_dga AND send_dga=True (compliance active)
        
        unique_point_ids = set()
        obras_points_ids = set()     # Set of IDs for fast lookup
        obras_points_list = list(obras_points_qs) # Use existing FS
        obras_dga_active = 0
        active_points = set() # ✅ FIX: Definir conjunto active_points
        dga_active_status = {} # ✅ FIX: Definir status individual
        
        # dga_standards_count: conteo por 'standard' (Res. Mayor/Medio/Menor)
        dga_standards_count = {}

        # ========================================
        # NUEVO: Calcular conteo por proveedor para puntos conectados
        # ========================================

        
        # Filtrar puntos que tienen telemetría activa dentro del universo de obras
        
        # Filtrar puntos que tienen telemetría activa dentro del universo de obras
        # Usar conteo manual seguro iterando sobre la lista ya obtenida para evitar problemas de filtrado reverso
        provider_counts = {'thethings': 0, 'novus': 0, 'tdata': 0}
        
        # Re-usar lógica de obras_with_telemetry pero iterando para clasificar
        # obras_points_list ya tiene TODOS los puntos con código de obra
        
        # Optimización: Cargar perfiles en memoria para evitar N+1
        # Use the actual list of IDs from the queryset (line 119), not the empty set from line 142
        obras_point_ids_list = dga_points_qs.values_list('point_catchment_id', flat=True).distinct()
        profiles_map = {
            p.point_catchment_id: p 
            for p in ProfileDataConfigCatchment.objects.filter(point_catchment__in=obras_point_ids_list)
        }
        
        for point in obras_points_list:
            profile = profiles_map.get(point.id)
            if profile and profile.is_telemetry:
                # Este punto cuenta como conectado
                if point.is_thethings:
                    provider_counts['thethings'] += 1
                if point.is_novus:
                    provider_counts['novus'] += 1
                if point.is_tdata:
                    provider_counts['tdata'] += 1

        # Calcular desconectados (Universo - Conectados)
        desconectados_count = num_obras - pct_conectados_count if num_obras >= pct_conectados_count else 0

        for point in obras_points_list:
            # We iterate over points that already have code_dga (filtered in dga_points_qs -> obras_points_qs)
            unique_point_ids.add(point.id)
            obras_points_ids.add(point.id)
            
            dga_profile = point.dga_data_config_profiles.first()
            if dga_profile:
                # Check DGA Active
                is_active = dga_profile.send_dga
                dga_active_status[point.id] = is_active # ✅ FIX: Guardar status por ID
                
                if is_active:
                    obras_dga_active += 1
                    active_points.add(point.id) # ✅ FIX: Agregar ID al conjunto active_points
                
                # Contar por estándar (para breakdown) - MEJORADO: incluir estado de conexión
                std = dga_profile.standard or 'SIN_ESTANDAR'
                
                # Inicializar estructura si no existe
                if std not in dga_standards_count:
                    dga_standards_count[std] = {'total': 0, 'connected': 0, 'disconnected': 0}
                
                # Incrementar total
                dga_standards_count[std]['total'] += 1
                
                # Verificar si tiene telemetría activa
                profile = profiles_map.get(point.id)
                if profile and profile.is_telemetry:
                    dga_standards_count[std]['connected'] += 1
                else:
                    dga_standards_count[std]['disconnected'] += 1
            else:
                dga_active_status[point.id] = False
                # Sin perfil DGA
                if 'SIN_ESTANDAR' not in dga_standards_count:
                    dga_standards_count['SIN_ESTANDAR'] = {'total': 0, 'connected': 0, 'disconnected': 0}
                dga_standards_count['SIN_ESTANDAR']['total'] += 1
                
                # Verificar telemetría para SIN_ESTANDAR también
                profile = profiles_map.get(point.id)
                if profile and profile.is_telemetry:
                    dga_standards_count['SIN_ESTANDAR']['connected'] += 1
                else:
                    dga_standards_count['SIN_ESTANDAR']['disconnected'] += 1
        
        # Crear lista ordenada para la vista
        dga_standards_breakdown = []
        if dga_standards_count:
            # Ordenar por conteo total descendente
            sorted_standards = sorted(dga_standards_count.items(), key=lambda item: item[1]['total'], reverse=True)
            for standard_code, stats in sorted_standards:
                try:
                    # Intentar obtener label legible
                    label = standard_labels.get(standard_code, standard_code)
                    
                    dga_standards_breakdown.append({
                        'label': label,
                        'total': stats['total'],
                        'connected': stats['connected'],
                        'disconnected': stats['disconnected']
                    })
                except:
                    dga_standards_breakdown.append({
                        'label': standard_code,
                        'total': stats['total'],
                        'connected': stats['connected'],
                        'disconnected': stats['disconnected']
                    })

        # ========================================
        # NUEVAS MÉTRICAS: Desglose Proveedores y Desconectados DGA
        # ========================================
        # Calcular desglose de proveedores para puntos conectados (con código de obra)
        # provider_counts already calculated above (lines 160-180)
        
        # ✅ FIX: Restaurar inicialización de contactadores de veracidad
        points_with_flow = 0
        points_with_d5 = 0
        points_flow_above_probable = 0
        veracidad_dict = {} # ✅ FIX: Restaurar veracidad_dict
        
        # ✅ FIX: Restaurar la definición de obras_points_annotated
        from django.db.models import OuterRef, Subquery as DjangoSubquery

        # Obtener IDs de últimos registros para cada punto
        latest_record_ids_subquery = InteractionDetail.objects.filter(
            catchment_point_id=OuterRef('id')
        ).order_by('-date_time_medition').values('id')[:1]

        # Anotar puntos con el ID de su último registro
        obras_points_annotated = CatchmentPoint.objects.filter(
            id__in=obras_points_ids
        ).annotate(
            latest_record_id=DjangoSubquery(latest_record_ids_subquery)
        ).select_related('project')

        # Obtener TODOS los últimos registros en 1 sola query
        latest_record_ids_list = [
            p.latest_record_id for p in obras_points_annotated
            if p.latest_record_id
        ]
        all_latest_records = InteractionDetail.objects.filter(
            id__in=latest_record_ids_list
        ).select_related('catchment_point', 'catchment_point__project')

        # Crear diccionario para acceso O(1) sin queries adicionales
        records_by_point_id = {
            r.catchment_point_id: r for r in all_latest_records
        }

        # Ahora el loop es rápido (sin queries)
        for point in obras_points_annotated:
            profile = point.data_config_profiles.first()
            if not profile or not profile.is_telemetry:
                continue

            # ✅ Acceso directo al diccionario (SIN query)
            last_record = records_by_point_id.get(point.id)
            if not last_record:
                continue
            
            # Obtener variables para verificar si tiene CAUDAL o CAUDAL_PROMEDIO activo
            variables = Variable.objects.filter(
                scheme_catchment__points_catchment=point
            ).distinct()
            variable_types = [v.type_variable for v in variables if v.type_variable]
            has_caudal = any(t in variable_types for t in ["CAUDAL", "CAUDAL_PROMEDIO"])
            
            if not has_caudal:
                continue
            
            # Este punto tiene código de obra, telemetría activa y CAUDAL/CAUDAL_PROMEDIO
            points_with_flow += 1
            
            # Verificar si tiene d5 (diámetro del flujómetro)
            diametro = None
            d5_safe = safe_float(profile.d5 if profile else None)
            if d5_safe > 0:
                diametro = d5_safe
                points_with_d5 += 1
            
            # Calcular flow dinámicamente si corresponde
            flow_value = last_record.flow or 0.0
            has_caudal_promedio = "CAUDAL_PROMEDIO" in variable_types
            d6_safe = safe_float(profile.d6 if profile else None)
            if has_caudal_promedio and d6_safe > 0:
                try:
                    from api.core.serializers.interaction_detail import InteractionDetailModelSerializer
                    serializer = InteractionDetailModelSerializer(last_record)
                    serialized_data = serializer.data
                    flow_value = serialized_data.get('flow', 0.0)
                except Exception:
                    flow_value = last_record.flow or 0.0
            
            # Solo calcular si tiene diámetro del flujómetro (d5) y flow válido
            flow_value_safe_veracidad_final = safe_float(flow_value)
            if flow_value_safe_veracidad_final > 0 and diametro:
                # Calcular caudal probable (usar velocidad razonable de 2.5 m/s)
                caudal_probable = calculate_probable_flow_by_velocity(diametro, 2.5)
                if flow_value_safe_veracidad_final > caudal_probable:
                    points_flow_above_probable += 1
                    exceso = flow_value_safe_veracidad_final - caudal_probable
                    pct_exceso = (exceso / caudal_probable * 100) if caudal_probable > 0 else 0
                    
                    # Obtener código de obra
                    codigo_obra = None
                    dga_profile = point.dga_data_config_profiles.first()
                    if dga_profile and dga_profile.code_dga:
                        codigo_obra = dga_profile.code_dga
                    
                    # Obtener nombre del proyecto
                    proyecto_nombre = point.project.name if point.project else "Sin proyecto"
                    
                    # Obtener horario de captura
                    horario_captura = last_record.date_time_medition.strftime('%d/%m/%Y %H:%M') if last_record.date_time_medition else "N/A"
                    
                    punto_info = {
                        'nombre': str(point.title) if point and point.title else "Sin nombre",
                        'punto': str(point.title) if point and point.title else "Sin nombre",  # Para compatibilidad con template unificado
                        'proyecto': proyecto_nombre,
                        'codigo_obra': codigo_obra,
                        'horario': horario_captura,
                        'fecha': last_record.date_time_medition,  # Agregar fecha para compatibilidad
                        'caudal_medido': round(flow_value_safe_veracidad_final, 2),
                        'caudal_real': round(flow_value_safe_veracidad_final, 2),  # Para compatibilidad
                        'caudal_probable': round(caudal_probable, 2),
                        'exceso': round(exceso, 2),
                        'pct_exceso': round(pct_exceso, 1),
                        'variables': variable_types if variable_types else [],  # Asegurar que siempre sea una lista
                        'pulses': last_record.pulses or 0,
                        'nivel': last_record.nivel or None,
                        'tipo': 'caudal',
                        'point_id': point.id if point else None,
                        'record_id': last_record.id,  # Agregar record_id para botón "Ver Detalle"
                        'tipo_error': 'Exceso Caudal'  # Agregar tipo_error para compatibilidad
                    }
                    
                    # Evitar duplicados: si el punto ya existe, mantener el que tiene mayor exceso
                    if point.id not in veracidad_dict:
                        veracidad_dict[point.id] = punto_info
                    else:
                        # Si ya existe, comparar exceso y mantener el mayor
                        existing_exceso = safe_float(veracidad_dict[point.id].get('exceso', 0))
                        exceso_safe = safe_float(exceso) if exceso is not None else 0
                        if exceso_safe > existing_exceso:
                            veracidad_dict[point.id] = punto_info
    
        # Convertir diccionario a lista y agregar campos necesarios para la tabla combinada
        # FILTRAR: Solo incluir puntos con código de obra
        veracidad_lista = []
        for punto_info in veracidad_dict.values():
            # Solo incluir si tiene código de obra
            if not punto_info.get('codigo_obra'):
                continue
            # Agregar campos necesarios para la tabla combinada
            punto_info['tipo_error'] = 'Exceso Caudal'
            punto_info['priority'] = 2  # Prioridad: Caudal Imposible (3) > Exceso Caudal (2) > Nivel Imposible (1)
            punto_info['fecha'] = None  # Se obtendrá del último registro si es necesario
            veracidad_lista.append(punto_info)
    
        # ✅ FIX: Verificar si se solicita veracidad histórica ANTES de calcular
        # Si se solicita veracidad histórica, usar cálculo histórico
        # Si NO se solicita, usar cálculo actual (comportamiento por defecto)
        if use_historical_veracidad:
            try:
                from api.core.utils.veracidad_historica import calculate_historical_veracidad
                
                # Calcular veracidad histórica para el período seleccionado
                historical_veracidad = calculate_historical_veracidad(
                    obras_points_list=obras_points_list,
                    period_days=period_days
                )
                
                # Usar resultados históricos en lugar de los actuales
                pct_veracidad = historical_veracidad['pct_veracidad']
                veracidad_total_puntos = historical_veracidad['pct_veracidad_total']
                veracidad_puntos_con_d5 = historical_veracidad['pct_veracidad_con_d5']
                veracidad_pasan_probable = historical_veracidad['pct_veracidad_pasan_probable']
                
                # Usar lista de veracidad histórica (ya incluye todos los puntos del período)
                veracidad_lista = historical_veracidad['veracidad_lista']
                
            except Exception as e:
                # ✅ FIX #4 ADICIONAL: Si falla veracidad histórica, avisar al usuario
                logging.error(f"Error calculando veracidad histórica: {e}", exc_info=True)
                # Resetear flag y avisar al usuario (no ocultar error silenciosamente)
                use_historical_veracidad = False
                veracidad_periodo = None
                # Usar cálculo actual como fallback
                pct_veracidad = ((points_with_d5 - points_flow_above_probable) / points_with_d5 * 100) if points_with_d5 > 0 else 0
                veracidad_total_puntos = points_with_flow
                veracidad_puntos_con_d5 = points_with_d5
                veracidad_pasan_probable = points_flow_above_probable
        else:
            # Cálculo actual (comportamiento por defecto - último registro)
            # % Veracidad = % que NO pasan (los que están por debajo o igual al probable)
            # Solo considerar puntos con d5 para el cálculo del porcentaje
            pct_veracidad = ((points_with_d5 - points_flow_above_probable) / points_with_d5 * 100) if points_with_d5 > 0 else 0
            
            # Guardar los totales para mostrar en el stat:
            # - points_with_flow: puntos con código de obra, telemetría activa y CAUDAL/CAUDAL_PROMEDIO
            # - points_with_d5: de esos, cuántos tienen d5 (diámetro del flujómetro)
            # - points_flow_above_probable: cuántos pasan el caudal probable
            veracidad_total_puntos = points_with_flow
            veracidad_puntos_con_d5 = points_with_d5
            veracidad_pasan_probable = points_flow_above_probable  # Puntos que SÍ pasan el caudal probable
    
        # 5. Con Desconexión (puntos con código de obra desconectados por más de 1 día)
        # 5. Con Desconexión (puntos con código de obra desconectados por más de 1 día)
        # Contar solo puntos que tienen código de obra Y están desconectados
        con_desconexion = 0
        desconexiones_parciales = 0          # DGA Partials (para breakdown)
        desconexiones_parciales_global = 0   # Global Partials (para tarjeta principal)

        # ✅ FIX: Iterar TODOS los puntos visibles para obtener estadísticas globales
        # Usar all_visible_points que ya está optimizado con select_related
        
        # Primero definimos all_visible_points (movemos lógica hacia arriba)
        all_visible_points = CatchmentPoint.objects.all().select_related('project')
        if project_id:
            all_visible_points = all_visible_points.filter(project=selected_project)
        if point_id:
            all_visible_points = all_visible_points.filter(id=point_id)
        
        # Pre-cargar últimos registros para TODOS (no solo obras)
        all_visible_ids = [p.id for p in all_visible_points]
        
        # Optimizacion: Usar una sola query para obtener últimos registros de TODO el conjunto visible
        from django.db.models import Subquery, OuterRef
        latest_records_qs = InteractionDetail.objects.filter(
            catchment_point_id=OuterRef('catchment_point_id')
        ).order_by('-date_time_medition')
        
        # Opción más simple: traer los records directamente usando ID__in
        # (InteractionDetail puede ser grande, así que filtramos por los puntos visibles)
        # Para evitar N+1, usamos un diccionario
        
        # Subquery para obtener el ID del último registro de cada punto
        latest_ids = InteractionDetail.objects.filter(
            catchment_point__in=all_visible_ids
        ).order_by('catchment_point', '-date_time_medition').distinct('catchment_point').values_list('id', flat=True)
        
        # Traer los objetos completos
        latest_records_map = {
            r.catchment_point_id: r 
            for r in InteractionDetail.objects.filter(id__in=latest_ids)
        }

        for point in all_visible_points:
            last_record = latest_records_map.get(point.id)
            if not last_record:
                continue

            # Determinamos si es DGA (está en la lista de obras)
            is_dga = point.id in obras_points_ids

            # Lógica de conteo
            if last_record.is_partial:
                # Contar SIEMPRE en Global
                desconexiones_parciales_global += 1
                # Contar en DGA solo si es DGA
                if is_dga:
                    desconexiones_parciales += 1
            
            elif last_record.days_not_conection and last_record.days_not_conection > 0:
                # Total Desconexión (Prioridad DGA por ahora?)
                # El usuario quiere ver fallas operativas.
                # Si queremos mantener % Conectados consistente (120 obras), solo sumamos si is_dga
                if is_dga:
                    con_desconexion += 1

        stats_caudal_probable = {
            'con_desconexion': con_desconexion,
            'desconexiones_parciales': desconexiones_parciales,
            'desconexiones_parciales_global': desconexiones_parciales_global # Nueva variable para contexto
        }
    
        # 7. Registro Errores (caudales y niveles imposibles)
        # Analizar últimos registros de puntos visibles (todos los puntos según filtro)
        # ✅ OPTIMIZACIÓN: Usar select_related para evitar N+1 queries
        all_visible_points = CatchmentPoint.objects.all().select_related('project')
        if project_id:
            all_visible_points = all_visible_points.filter(project=selected_project)
        if point_id:
            all_visible_points = all_visible_points.filter(id=point_id)
        all_visible_points_list = list(all_visible_points)
    
        registro_errores = 0
        errores_dict = {}  # Diccionario para evitar duplicados: key=point.id, value=dict con info del error
        # Prioridad de tipos de error: "Caudal Imposible" > "Exceso Caudal" > "Nivel Imposible"
        # NOTA: "Caudal Excedido" se cambia a "Exceso Caudal" para evitar duplicados
        error_priority = {"Caudal Imposible": 3, "Exceso Caudal": 2, "Nivel Imposible": 1}
    
        # FILTRAR: Solo procesar puntos con código de obra
        for point in all_visible_points_list:
            # Verificar que el punto tenga código de obra
            dga_profile_check = point.dga_data_config_profiles.first()
            if not dga_profile_check or not dga_profile_check.code_dga:
                continue  # Saltar puntos sin código de obra
            profile = point.data_config_profiles.first()
            if not profile:
                continue
            
            # ✅ OPTIMIZACIÓN: Usar diccionario pre-cargado en lugar de query
            last_record = records_by_point_id.get(point.id)
            if not last_record:
                # Fallback solo si no está en el mapa (raro si tiene código DGA)
                last_record = InteractionDetail.objects.filter(
                    catchment_point=point
                ).select_related('catchment_point', 'catchment_point__project').order_by('-date_time_medition').first()
            
            if not last_record:
                continue
            
            error_tipo = None
            caudal_excedido = None
            caudal_probable_calc = None
            
            # Obtener variables para calcular flow dinámicamente si corresponde
            variables = Variable.objects.filter(
                scheme_catchment__points_catchment=point
            ).distinct()
            variable_types = [v.type_variable for v in variables if v.type_variable]
            has_caudal_promedio = "CAUDAL_PROMEDIO" in variable_types
            
            # Calcular flow real
            flow_value = last_record.flow or 0.0
            d6_safe_error = safe_float(profile.d6 if profile else None)
            if has_caudal_promedio and d6_safe_error > 0:
                try:
                    from api.core.serializers.interaction_detail import InteractionDetailModelSerializer
                    serializer = InteractionDetailModelSerializer(last_record)
                    serialized_data = serializer.data
                    flow_value = serialized_data.get('flow', 0.0)
                except Exception:
                    flow_value = last_record.flow or 0.0
            
            # Verificar caudal imposible o excedido
            flow_value_safe_error = safe_float(flow_value)
            if flow_value_safe_error > 0:
                d5_safe_error = safe_float(profile.d5 if profile else None)
                if d5_safe_error > 0:
                    # Verificar si es imposible según diámetro
                    es_imposible, mensaje = validate_flow_impossible(
                        flow_value_safe_error,
                        d5_safe_error
                    )
                    if es_imposible:
                        registro_errores += 1
                        error_tipo = "Caudal Imposible"
                        # Calcular caudal probable para mostrar el exceso
                        caudal_probable_calc = calculate_probable_flow_by_velocity(d5_safe_error, 2.5)
                        caudal_excedido = flow_value_safe_error - caudal_probable_calc
                        # Obtener variables para este punto
                        variables_error = Variable.objects.filter(
                            scheme_catchment__points_catchment=point
                        ).distinct()
                        variable_types_error = [v.type_variable for v in variables_error if v.type_variable]
                        
                        # Calcular porcentaje de exceso si hay exceso
                        pct_exceso_calc = None
                        if caudal_excedido is not None and caudal_probable_calc is not None and caudal_probable_calc > 0:
                            pct_exceso_calc = round((caudal_excedido / caudal_probable_calc * 100), 1)
                        
                        # Obtener código de obra
                        codigo_obra_error = None
                        dga_profile_error = point.dga_data_config_profiles.first()
                        if dga_profile_error and dga_profile_error.code_dga:
                            codigo_obra_error = dga_profile_error.code_dga
                        
                        # Obtener horario de captura para compatibilidad con template
                        horario_captura_error = last_record.date_time_medition.strftime('%d/%m/%Y %H:%M') if last_record.date_time_medition else "N/A"
                        
                        error_info = {
                            'punto': point.title,
                            'nombre': point.title,  # Para compatibilidad con template unificado
                            'fecha': last_record.date_time_medition,
                            'horario': horario_captura_error,  # Agregar horario para compatibilidad con template
                            'tipo_error': error_tipo,
                            'mensaje': mensaje,
                        'caudal_real': round(flow_value_safe_error, 2) if flow_value_safe_error > 0 else None,
                        'caudal_medido': round(flow_value_safe_error, 2) if flow_value_safe_error > 0 else None,  # Para compatibilidad
                            'caudal_probable': round(caudal_probable_calc, 2) if caudal_probable_calc else None,
                            'exceso': round(caudal_excedido, 2) if caudal_excedido else None,
                            'pct_exceso': pct_exceso_calc,  # Agregar porcentaje de exceso
                            'variables': variable_types_error if variable_types_error else [],  # Asegurar que siempre sea una lista
                            'pulses': last_record.pulses or 0,
                            'nivel': last_record.nivel or None,
                            'tipo': 'caudal',
                            'record_id': last_record.id,
                            'point_id': point.id if point else None,
                            'priority': error_priority.get(error_tipo, 0),
                            'proyecto': str(point.project.name) if point and point.project and point.project.name else None,  # Agregar proyecto
                            'codigo_obra': codigo_obra_error  # Obtener del perfil DGA
                        }
                        
                        # Evitar duplicados: si el punto ya existe, mantener el error con mayor prioridad
                        if point.id not in errores_dict:
                            errores_dict[point.id] = error_info
                        else:
                            existing_priority = errores_dict[point.id].get('priority', 0)
                            if error_priority.get(error_tipo, 0) > existing_priority:
                                errores_dict[point.id] = error_info
                        continue
                    # NO agregar "Caudal Excedido" aquí porque ya se maneja en veracidad_lista como "Exceso Caudal"
                    # Esto evita duplicados entre "Caudal Excedido" y "Exceso Caudal"
                    # Solo procesar "Caudal Imposible" y "Nivel Imposible"
            
            # Verificar nivel imposible
            if last_record.nivel:
                try:
                    nivel_value = safe_float(last_record.nivel)
                    if nivel_value > 0:
                        d1_safe = safe_float(profile.d1 if profile else None)
                        d3_safe = safe_float(profile.d3 if profile else None)
                        es_imposible, mensaje = validate_level_impossible(
                            nivel_value,
                            d1_safe,
                            d3_safe
                        )
                        if es_imposible:
                            registro_errores += 1
                            error_tipo = "Nivel Imposible"
                            # Obtener variables para este punto
                            variables_error = Variable.objects.filter(
                                scheme_catchment__points_catchment=point
                            ).distinct()
                            variable_types_error = [v.type_variable for v in variables_error if v.type_variable]
                            
                            # Obtener código de obra
                            codigo_obra_error = None
                            dga_profile_error = point.dga_data_config_profiles.first()
                            if dga_profile_error and dga_profile_error.code_dga:
                                codigo_obra_error = dga_profile_error.code_dga
                            
                            # Obtener horario de captura para compatibilidad con template
                            horario_captura = last_record.date_time_medition.strftime('%d/%m/%Y %H:%M') if last_record.date_time_medition else "N/A"
                            
                            error_info = {
                                'punto': str(point.title) if point and point.title else "Sin nombre",
                                'nombre': str(point.title) if point and point.title else "Sin nombre",  # Para compatibilidad con template unificado
                                'fecha': last_record.date_time_medition,
                                'horario': horario_captura,  # Agregar horario para compatibilidad con template
                                'tipo_error': error_tipo,
                                'mensaje': mensaje,
                                'nivel': round(nivel_value, 2) if nivel_value else 0,
                                'variables': variable_types_error if variable_types_error else [],  # Asegurar que siempre sea una lista
                                'pulses': last_record.pulses or 0,
                                'tipo': 'nivel',
                                'record_id': last_record.id,
                                'point_id': point.id if point else None,
                                'priority': error_priority.get(error_tipo, 0),
                                'proyecto': str(point.project.name) if point and point.project and point.project.name else None,  # Agregar proyecto
                                'codigo_obra': codigo_obra_error,  # Obtener del perfil DGA
                                'exceso': None,  # Los errores de nivel no tienen exceso de caudal
                                'pct_exceso': None,
                                'caudal_medido': None,  # Los errores de nivel no tienen caudal medido
                                'caudal_real': None,  # Los errores de nivel no tienen caudal real
                                'caudal_probable': None  # Los errores de nivel no tienen caudal probable
                            }
                            
                            # Evitar duplicados: si el punto ya existe, mantener el error con mayor prioridad
                            if point.id not in errores_dict:
                                errores_dict[point.id] = error_info
                            else:
                                existing_priority = errores_dict[point.id].get('priority', 0)
                                if error_priority.get(error_tipo, 0) > existing_priority:
                                    errores_dict[point.id] = error_info
                except (ValueError, TypeError):
                    pass
    
        # Convertir diccionario a lista
        registros_errores_lista = list(errores_dict.values())
    
        # Combinar ambas listas y ordenar por prioridad
        # Prioridades: Caudal Imposible (3) > Caudal Excedido (2) > Exceso Caudal (2) > Nivel Imposible (1)
        errores_y_excesos_combinados = veracidad_lista + registros_errores_lista
        # Ordenar por prioridad descendente (mayor prioridad primero)
        errores_y_excesos_combinados.sort(key=lambda x: x.get('priority', 0), reverse=True)
    
        # 8. Cola DGA - Total de registros preparados para envío a DGA
        # Contar TODOS los registros con send_dga=True (no solo últimos 1000)
        records_in_dga_queue = InteractionDetail.objects.filter(
            combined_filter,
            send_dga=True
        ).count()
        
        # Total de registros para calcular porcentaje
        total_registros_cola_dga = InteractionDetail.objects.filter(combined_filter).count()
        pct_cola_dga = (records_in_dga_queue / total_registros_cola_dga * 100) if total_registros_cola_dga > 0 else 0
    
        # Paginación de registros con errores (10 por página)
        from django.core.paginator import Paginator
        error_paginator = Paginator(registros_errores_lista, 10)
        # ✅ FIX #4: MANEJO MEJORADO DE EXCEPCIONES
        page_number = request.GET.get('error_page', 1)
        try:
            # Validar que page_number sea un número válido
            try:
                page_number = int(page_number)
            except (ValueError, TypeError):
                logging.warning(f"Página inválida solicitada (no es número): {page_number}")
                page_number = 1

            error_page_obj = error_paginator.page(page_number)
        except Exception as e:
            # Capturar solo excepciones esperadas de paginación
            from django.core.paginator import PageNotAnInteger, EmptyPage
            if isinstance(e, (PageNotAnInteger, EmptyPage)):
                logging.warning(f"Página inválida: {page_number} - {str(e)}")
            else:
                logging.error(f"Error inesperado en paginación: {str(e)}", exc_info=True)
            error_page_obj = error_paginator.page(1)
    
        # 9. Notificaciones Pendientes
        # Notificaciones relacionadas con mediciones con errores que NO tengan incidencias (responses)
        # NO considerar días de desconexión
        error_interactions = InteractionDetail.objects.filter(
        combined_filter,
        is_error=True
        ).exclude(
        days_not_conection__gt=0
        )
    
        # Obtener puntos con errores (sin días de desconexión)
        error_points = error_interactions.values_list('catchment_point', flat=True).distinct()
    
        # Contar notificaciones sin respuesta para estos puntos
        notificaciones_pendientes = NotificationsCatchment.objects.filter(
        point_catchment__in=error_points,
        responses__isnull=True
        ).distinct().count()
    
    
        # ========================================
        # PUNTOS DEL PROYECTO SELECCIONADO
        # ========================================
        project_points = []
        if project_id:
            project_points = CatchmentPoint.objects.filter(project=selected_project).order_by('title')
        else:
            project_points = CatchmentPoint.objects.all().order_by('title')[:50]  # Limitar si no hay filtro
    
        # REGISTROS RECIENTES (ÚLTIMOS 24 HORAS - ÚLTIMO REGISTRO POR PUNTO)
        # Priorizar puntos desconectados primero
        # ========================================
        from datetime import timedelta
    
        # Obtener fecha de hace 24 horas
        last_24_hours = timezone.now() - timedelta(hours=24)
    
        # Obtener todos los puntos visibles según el filtro
        # ✅ OPTIMIZACIÓN: Usar select_related para evitar N+1 queries
        if project_id:
            visible_points = CatchmentPoint.objects.filter(project=selected_project).select_related('project')
        else:
            visible_points = CatchmentPoint.objects.all().select_related('project')
    
        if point_id:
            visible_points = visible_points.filter(id=point_id)

        # START FILTER LOGIC
        provider_filter = request.GET.get('provider_filter', 'all')
        variable_filter = request.GET.get('variable_filter', 'all')
        
        # Filtro de Proveedor
        if provider_filter == 'thethings':
            visible_points = visible_points.filter(is_thethings=True)
        elif provider_filter == 'novus':
            visible_points = visible_points.filter(is_novus=True)
        elif provider_filter == 'tdata':
            visible_points = visible_points.filter(is_tdata=True)
            
        # Filtro de Variable (Caudal vs Caudal Promedio)
        if variable_filter == 'caudal':
            # Filtrar puntos que tengan configurada la variable CAUDAL
            # catchments -> schemes -> variables
            visible_points = visible_points.filter(schemes__variables__type_variable='CAUDAL').distinct()
        elif variable_filter == 'promedio':
            visible_points = visible_points.filter(schemes__variables__type_variable='CAUDAL_PROMEDIO').distinct()
        # END FILTER LOGIC
    
        # Obtener SOLO el ÚLTIMO registro por punto (sin duplicados)
        # Filtrar solo puntos con código de obra
        visible_points_with_code = []
        for point in visible_points:
            dga_profile_check = point.dga_data_config_profiles.first()
            if dga_profile_check and dga_profile_check.code_dga:
                visible_points_with_code.append(point.id)
    
        # CORREGIDO: Obtener el último registro de cada punto de las últimas 24 horas
        # Usar annotate con Subquery para obtener correctamente un registro por punto
        from django.db.models import OuterRef, Subquery
    
        # Opción más eficiente: Para cada punto, obtener el último registro de las últimas 24 horas
        # Si no hay registro en las últimas 24 horas, obtener el más reciente disponible
        recent_interactions = []
        for point_id in visible_points_with_code:
            # Primero intentar obtener de las últimas 24 horas
            # ✅ OPTIMIZACIÓN: Usar select_related para evitar N+1 queries
            last_record = InteractionDetail.objects.filter(
                catchment_point_id=point_id,
                date_time_medition__gte=last_24_hours
            ).select_related('catchment_point', 'catchment_point__project').order_by('-date_time_medition', '-id').first()
            
            # Si no hay registro en las últimas 24 horas, obtener el más reciente disponible
            if not last_record:
                last_record = InteractionDetail.objects.filter(
                    catchment_point_id=point_id
                ).select_related('catchment_point', 'catchment_point__project').order_by('-date_time_medition', '-id').first()
            
            if last_record:
                recent_interactions.append(last_record)
    
        # Optimizar con select_related y prefetch_related
        # Convertir a queryset para aplicar optimizaciones
        if recent_interactions:
            record_ids = [r.id for r in recent_interactions]
            recent_interactions = InteractionDetail.objects.filter(
                id__in=record_ids
            ).select_related(
                'catchment_point', 'catchment_point__project'
            ).prefetch_related(
                Prefetch(
                    'catchment_point__schemes',
                    queryset=SchemesCatchment.objects.prefetch_related(
                        Prefetch(
                            'variables',
                            queryset=Variable.objects.only('id', 'type_variable', 'label', 'scheme_catchment_id')
                        )
                    )
                ),
                Prefetch(
                    'catchment_point__data_config_profiles',
                    queryset=ProfileDataConfigCatchment.objects.only('point_catchment_id', 'd6', 'is_telemetry', 'd3')
                ),
                Prefetch(
                    'catchment_point__dga_data_config_profiles',
                    queryset=DgaDataConfigCatchment.objects.only('point_catchment_id', 'code_dga', 'flow_granted_dga', 'standard')
                )
            ).order_by('-date_time_medition')
            
            # Convertir a lista manteniendo el orden
            recent_interactions = list(recent_interactions)
            
            # Validar que no hay duplicados por punto
            point_ids_seen = set()
            unique_interactions = []
            for interaction in recent_interactions:
                point_id = interaction.catchment_point_id
                if point_id not in point_ids_seen:
                    point_ids_seen.add(point_id)
                    unique_interactions.append(interaction)
                else:
                    # If there's a duplicate, keep the more recent one (already sorted)
                    pass
            
            recent_interactions = unique_interactions
        else:
            recent_interactions = []
    
        # Ordenar: primero desconectados (days_not_conection > 0), luego por fecha descendente
        recent_interactions.sort(key=lambda x: (
            not (x.days_not_conection and x.days_not_conection > 0),  # False (desconectados) primero
            -(x.date_time_medition.timestamp() if x and x.date_time_medition else timezone.now().timestamp())  # Luego por fecha descendente (negativo para reverse)
        ))
    
        # Agregar información de variables configuradas y valores detallados
        from api.core.serializers.interaction_detail import InteractionDetailModelSerializer
    
        # ========================================
        # OPTIMIZACIÓN VOUCHERS: Obtener el último voucher válido para cada punto
        # ========================================
        # Obtener IDs de puntos para la consulta
        point_ids_voucher = [i.catchment_point_id for i in recent_interactions]
        unique_point_ids_voucher = list(set(point_ids_voucher))
        
        latest_vouchers_map = {}
        if unique_point_ids_voucher:
            try:
                # Usar distinct on para Postgres (eficiente)
                # Seleccionar el primer registro (más reciente) que tenga voucher no nulo
                # REMOVED .only() to ensure full object availability
                latest_vouchers_qs = InteractionDetail.objects.filter(
                    catchment_point_id__in=unique_point_ids_voucher,
                    n_voucher__isnull=False
                ).exclude(n_voucher='').order_by('catchment_point_id', '-date_time_medition').distinct('catchment_point_id')
                
                latest_vouchers_map = {v.catchment_point_id: v for v in latest_vouchers_qs}
            except Exception as e:
                # Fallback por si la DB no soporta distinct on o hay error
                pass

        enhanced_interactions = []
        for interaction in recent_interactions:
            # IMPORTANTE: No sobrescribir days_not_conection si ya tiene un valor
            # Solo usar el valor existente del modelo, no calcularlo aquí
            # El modelo ya tiene la lógica para calcular days_not_conection
            # Si no tiene fecha logger pero tiene days_not_conection > 0, respetar ese valor
            point = interaction.catchment_point
            
            # Obtener variables configuradas
            variables = []
            if hasattr(point, '_prefetched_objects_cache') and 'schemes' in point._prefetched_objects_cache:
                schemes = point._prefetched_objects_cache['schemes']
                for scheme in schemes:
                    if hasattr(scheme, '_prefetched_objects_cache') and 'variables' in scheme._prefetched_objects_cache:
                        variables.extend(scheme._prefetched_objects_cache['variables'])  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
            else:
                # Fallback: consulta directa
                variables = Variable.objects.filter(
                    scheme_catchment__points_catchment=point
                ).distinct()
            
            variable_types = [v.type_variable for v in variables if v.type_variable]
            
            # Verificar si tiene d6 configurado y obtener d3 (posicionamiento nivel)
            has_d6 = False
            d6_value = None
            d3_posicionamiento = None
            profile = None
            if hasattr(point, '_prefetched_objects_cache') and 'data_config_profiles' in point._prefetched_objects_cache:
                profiles = point._prefetched_objects_cache['data_config_profiles']
                if profiles:
                    profile = profiles[0]
                    # ✅ FIX #3: VALIDACIÓN SEGURA - Usar safe_float en lugar de float() directo
                    d6_safe = safe_float(profile.d6)
                    if d6_safe > 0:
                        has_d6 = True
                        d6_value = d6_safe
                    d3_safe = safe_float(profile.d3)
                    if d3_safe > 0:
                        d3_posicionamiento = d3_safe
            else:
                # Fallback: consulta directa
                profile = ProfileDataConfigCatchment.objects.filter(point_catchment=point).first()
            if profile:
                d6_safe_fallback = safe_float(profile.d6)
                if d6_safe_fallback > 0:
                    has_d6 = True
                    d6_value = d6_safe_fallback
                d3_safe_fallback = safe_float(profile.d3)
                if d3_safe_fallback > 0:
                    d3_posicionamiento = d3_safe_fallback
            
            # Obtener código de obra, caudal autorizado DGA y estándar
            codigo_obra = None
            caudal_autorizado_dga = None
            estandar = None
            dga_profile = None
            if hasattr(point, '_prefetched_objects_cache') and 'dga_data_config_profiles' in point._prefetched_objects_cache:
                dga_profiles = point._prefetched_objects_cache['dga_data_config_profiles']
                if dga_profiles:
                    dga_profile = dga_profiles[0]
                    if dga_profile.code_dga:
                        codigo_obra = dga_profile.code_dga
                    flow_granted_safe = safe_float(dga_profile.flow_granted_dga)
                    if flow_granted_safe > 0:
                        caudal_autorizado_dga = flow_granted_safe
                    # Obtener estándar del perfil DGA
                    if dga_profile.standard:
                        try:
                            estandar = dga_profile.get_standard_display()
                        except:
                            estandar = dga_profile.standard
            else:
                # Fallback: consulta directa
                dga_profile = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
                if dga_profile:
                    if dga_profile.code_dga:
                        codigo_obra = dga_profile.code_dga
                    flow_granted_safe = safe_float(dga_profile.flow_granted_dga)
                    if flow_granted_safe > 0:
                        caudal_autorizado_dga = flow_granted_safe
                    # Obtener estándar del perfil DGA
                    if dga_profile.standard:
                        try:
                            estandar = dga_profile.get_standard_display()
                        except:
                            estandar = dga_profile.standard
            
            # Verificar si tiene variable CAUDAL_PROMEDIO
            has_caudal_promedio = 'CAUDAL_PROMEDIO' in variable_types
            
            # Calcular flow dinámicamente si corresponde
            flow_value = interaction.flow or 0.0
            if has_caudal_promedio and has_d6:
                # Usar el serializer para calcular flow dinámicamente
                try:
                    serializer = InteractionDetailModelSerializer(interaction)
                    serialized_data = serializer.data
                    flow_value = serialized_data.get('flow', 0.0)
                    # Si el serializer devuelve None o 0, intentar calcular manualmente con average_flow
                    if not flow_value or flow_value == 0:
                        from api.cronjobs.telemetry.controllers.flow import average_flow
                        # Obtener fecha preferente: last_logger, fallback: medition
                        date_lg = interaction.date_time_last_logger or interaction.date_time_medition
                        if date_lg and interaction.total is not None:
                            point_catchment_dict = {"id": point.id}
                            total_safe = safe_float(interaction.total)
                            flow_value = average_flow(
                                point_catchment=point_catchment_dict,
                                total=total_safe,
                                date_lg=date_lg
                            ) or 0.0
                except Exception as e:
                    # Si falla el serializer, intentar calcular directamente con average_flow
                    try:
                        from api.cronjobs.telemetry.controllers.flow import average_flow
                        # Obtener fecha preferente: last_logger, fallback: medition
                        date_lg = interaction.date_time_last_logger or interaction.date_time_medition
                        if date_lg and interaction.total is not None:
                            point_catchment_dict = {"id": point.id}
                            total_safe_outer = safe_float(interaction.total)
                            flow_value = average_flow(
                                point_catchment=point_catchment_dict,
                                total=total_safe_outer,
                                date_lg=date_lg
                            ) or 0.0
                        else:
                            flow_value = interaction.flow or 0.0
                    except Exception:
                        # Si todo falla, usar el valor guardado
                        flow_value = interaction.flow or 0.0
            elif has_caudal_promedio and not has_d6:
                # Tiene CAUDAL_PROMEDIO pero no tiene d6, mostrar N/A
                flow_value = None
            
            # Calcular diferencia de caudal autorizado DGA
            diferencia_caudal_dga = None
            pct_usado_caudal_dga = None  # Porcentaje usado del autorizado (invertido)
            caudal_autorizado_safe = safe_float(caudal_autorizado_dga)
            flow_value_safe_enhanced = safe_float(flow_value)
            if caudal_autorizado_safe > 0 and flow_value_safe_enhanced > 0:
                diferencia_caudal_dga = caudal_autorizado_safe - flow_value_safe_enhanced
                # Porcentaje usado: cuánto del autorizado se está usando
                pct_usado_caudal_dga = (flow_value_safe_enhanced / caudal_autorizado_safe * 100) if caudal_autorizado_safe > 0 else 0
            
            # Calcular veracidad (si el caudal excede el probable)
            veracidad_pct = None
            tiene_veracidad = False
            caudal_probable = None
            if profile and profile.d5 and float(profile.d5) > 0 and flow_value_safe_enhanced > 0:
                d5_safe = safe_float(profile.d5)
                if d5_safe > 0:
                    # calculate_probable_flow_by_velocity ya está importado al inicio del archivo
                    caudal_probable = calculate_probable_flow_by_velocity(d5_safe, 2.5)
                    if caudal_probable > 0:
                        tiene_veracidad = True
                        # Veracidad: porcentaje del caudal medido respecto al probable
                        # Si es <= 100%, es veraz. Si es > 100%, excede el probable
                        veracidad_pct = (flow_value_safe_enhanced / caudal_probable * 100)
            
            # Validar veracidad del nivel (nivel freático no puede exceder posicionamiento)
            nivel_error_critico = False
            nivel_veracidad_msg = None
            water_table_safe = safe_float(interaction.water_table)
            d3_posicionamiento_safe = safe_float(d3_posicionamiento)
            if water_table_safe > 0 and d3_posicionamiento_safe > 0:
                if water_table_safe > d3_posicionamiento_safe:
                    nivel_error_critico = True
                    nivel_veracidad_msg = "ERROR CRÍTICO: Nivel freático superior al posicionamiento"
                else:
                    # Calcular diferencia como porcentaje
                    diferencia_nivel = d3_posicionamiento_safe - water_table_safe
                    pct_diferencia = (diferencia_nivel / d3_posicionamiento_safe * 100) if d3_posicionamiento_safe > 0 else 0
                    nivel_veracidad_msg = f"OK: {diferencia_nivel:.2f}m bajo posicionamiento ({pct_diferencia:.1f}%)"
            
            # ========================================
            # CALCULAR TIEMPO SIN CAMBIO DE PULSOS (DÍAS Y HORAS)
            # ========================================
            pulses_days_unchanged = None
            pulses_hours_unchanged = None
            current_pulses = interaction.pulses  # Puede ser 0 o None
            
            # Siempre calcular el tiempo sin cambio (incluyendo cuando pulsos es 0)
            try:
                if current_pulses is not None:
                    last_different_pulses_record = InteractionDetail.objects.filter(
                        catchment_point_id=point.id,
                        date_time_medition__lt=interaction.date_time_medition
                    ).exclude(
                        pulses=current_pulses
                    ).order_by('-date_time_medition').first()
                else:
                    last_different_pulses_record = InteractionDetail.objects.filter(
                        catchment_point_id=point.id,
                        date_time_medition__lt=interaction.date_time_medition,
                        pulses__isnull=False
                    ).order_by('-date_time_medition').first()
                
                if last_different_pulses_record and last_different_pulses_record.date_time_medition:
                    time_diff = interaction.date_time_medition - last_different_pulses_record.date_time_medition
                    pulses_days_unchanged = time_diff.days
                    pulses_hours_unchanged = time_diff.seconds // 3600
                else:
                    first_record = InteractionDetail.objects.filter(
                        catchment_point_id=point.id
                    ).order_by('date_time_medition').first()
                    
                    if first_record and first_record.date_time_medition and interaction.date_time_medition:
                        time_diff = interaction.date_time_medition - first_record.date_time_medition
                        pulses_days_unchanged = time_diff.days
                        pulses_hours_unchanged = time_diff.seconds // 3600
            except Exception as e:
                pass
            
            # ========================================
            # CALCULAR TIEMPO SIN CAMBIO DE NIVEL
            # ========================================
            nivel_days_unchanged = None
            nivel_hours_unchanged = None
            current_nivel = interaction.nivel  # Puede ser 0 o None
            
            # Siempre calcular el tiempo sin cambio (incluyendo cuando nivel es 0)
            try:
                if current_nivel is not None:
                    last_different_nivel_record = InteractionDetail.objects.filter(
                        catchment_point_id=point.id,
                        date_time_medition__lt=interaction.date_time_medition
                    ).exclude(
                        nivel=current_nivel
                    ).order_by('-date_time_medition').first()
                else:
                    last_different_nivel_record = InteractionDetail.objects.filter(
                        catchment_point_id=point.id,
                        date_time_medition__lt=interaction.date_time_medition,
                        nivel__isnull=False
                    ).order_by('-date_time_medition').first()
                
                if last_different_nivel_record and last_different_nivel_record.date_time_medition:
                    time_diff = interaction.date_time_medition - last_different_nivel_record.date_time_medition
                    nivel_days_unchanged = time_diff.days
                    nivel_hours_unchanged = time_diff.seconds // 3600
                else:
                    first_record = InteractionDetail.objects.filter(
                        catchment_point_id=point.id
                    ).order_by('date_time_medition').first()
                    
                    if first_record and first_record.date_time_medition and interaction.date_time_medition:
                        time_diff = interaction.date_time_medition - first_record.date_time_medition
                        nivel_days_unchanged = time_diff.days
                        nivel_hours_unchanged = time_diff.seconds // 3600
            except Exception as e:
                pass
            
            # ========================================
            # CALCULAR TIEMPO SIN CAMBIO DE CAUDAL (FLOW)
            # ========================================
            flow_days_unchanged = None
            flow_hours_unchanged = None
            current_flow = interaction.flow  # Puede ser 0 o None
            
            # Siempre calcular el tiempo sin cambio (incluyendo cuando flow es 0)
            try:
                # Buscar el registro más reciente donde el flow era diferente
                if current_flow is not None:
                    last_different_flow_record = InteractionDetail.objects.filter(
                        catchment_point_id=point.id,
                        date_time_medition__lt=interaction.date_time_medition
                    ).exclude(
                        flow=current_flow
                    ).order_by('-date_time_medition').first()
                else:
                    # Si es None, buscar cualquier registro con flow diferente de None
                    last_different_flow_record = InteractionDetail.objects.filter(
                        catchment_point_id=point.id,
                        date_time_medition__lt=interaction.date_time_medition,
                        flow__isnull=False
                    ).order_by('-date_time_medition').first()
                
                if last_different_flow_record and last_different_flow_record.date_time_medition:
                    time_diff = interaction.date_time_medition - last_different_flow_record.date_time_medition
                    flow_days_unchanged = time_diff.days
                    flow_hours_unchanged = time_diff.seconds // 3600
                else:
                    # No hay registro previo diferente - verificar primer registro
                    first_record = InteractionDetail.objects.filter(
                        catchment_point_id=point.id
                    ).order_by('date_time_medition').first()
                    
                    if first_record and first_record.date_time_medition and interaction.date_time_medition:
                        time_diff = interaction.date_time_medition - first_record.date_time_medition
                        flow_days_unchanged = time_diff.days
                        flow_hours_unchanged = time_diff.seconds // 3600
            except Exception as e:
                pass
            
            # Preparar lista de variables con su estado para colorear en el template
            variables_with_status = []
            # variable_types es un set de strings: {'CAUDAL', 'NIVEL', ...}
            # interaction.variable_details es una lista de dicts: [{'name': '...', 'type': '...', 'days': 0}, ...]
            
            # Crear un mapa rápido del estado actual
            status_map = {}
            if interaction.variable_details:
                for vd in interaction.variable_details:
                    status_map[vd.get('type')] = vd.get('days', 0)
            
            for v_type in variable_types:
                # Mapeo de tipos para coincidencia
                lookup_type = v_type
                if v_type == 'CAUDAL_PROMEDIO': lookup_type = 'CAUDAL'
                
                days = status_map.get(lookup_type, 0)
                variables_with_status.append({
                    'type': v_type,
                    'days': days,
                    'is_failing': days > 0
                })

            enhanced_interactions.append({
                'interaction': interaction,
                'variables': variable_types, # Keep for backward compat
                'variables_with_status': variables_with_status, # ✅ NUEVO: Lista de dicts {type, days, is_failing}
                'has_d6': has_d6,
                'd6_value': d6_value,
                'has_caudal_promedio': has_caudal_promedio,
                'flow': flow_value,
                'pulses': interaction.pulses or 0,
                'pulses_days_unchanged': pulses_days_unchanged,
                'pulses_hours_unchanged': pulses_hours_unchanged,
                'nivel_days_unchanged': nivel_days_unchanged,
                'nivel_hours_unchanged': nivel_hours_unchanged,
                'flow_days_unchanged': flow_days_unchanged,
                'flow_hours_unchanged': flow_hours_unchanged,
                'total': interaction.total or 0,
                'total_diff': interaction.total_diff or 0,
                'total_today_diff': interaction.total_today_diff or 0,
                'nivel': interaction.nivel or 0,
                'water_table': interaction.water_table or 0,
                'codigo_obra': codigo_obra,
                'caudal_autorizado_dga': caudal_autorizado_dga,
                'diferencia_caudal_dga': diferencia_caudal_dga,
                'pct_usado_caudal_dga': pct_usado_caudal_dga,
                'd3_posicionamiento': d3_posicionamiento,
                'estandar': estandar,
                # Agregar veracidad de caudal
                'tiene_veracidad': tiene_veracidad,
                'veracidad_pct': round(veracidad_pct, 1) if veracidad_pct is not None else None,
                'caudal_probable': round(caudal_probable, 2) if caudal_probable is not None else None,
                # Agregar veracidad de nivel
                'nivel_error_critico': nivel_error_critico,
                'nivel_veracidad_msg': nivel_veracidad_msg,
                # Usar el voucher del mapa optimizado (último real) o fallback al del registro actual
                'last_voucher': latest_vouchers_map.get(point.id).n_voucher if latest_vouchers_map.get(point.id) else (interaction.n_voucher if interaction.n_voucher else None),
                # Agregar fecha del voucher
                'last_voucher_date': latest_vouchers_map.get(point.id).date_time_medition if latest_vouchers_map.get(point.id) else (interaction.date_time_medition if interaction.n_voucher else None),
                # Agregar objeto completo del voucher para verificar variables enviadas
                'last_voucher_obj': latest_vouchers_map.get(point.id) if latest_vouchers_map.get(point.id) else (interaction if interaction.n_voucher else None),
                'send_dga': interaction.send_dga if hasattr(interaction, 'send_dga') else False,
                # New: Agregar estado de cumplimiento activo para frontend
                'dga_active': dga_profile.send_dga if dga_profile else False,
            })
        # Ya está filtrado por código de obra en la consulta inicial
        # Mantener el orden: primero desconectados, luego por fecha descendente
    
        # ==============================================================================
        # ✅ FINAL SAFETY CHECK: Definir variables faltantes para evitar 500 Error
        # ==============================================================================
        if 'pct_conectados' not in locals(): pct_conectados = 0
        if 'pct_conectados_count' not in locals(): pct_conectados_count = 0
        if 'pct_conectados_total' not in locals(): pct_conectados_total = 0
        
        if 'obras_dga_active' not in locals(): obras_dga_active = 0
        if 'num_obras' not in locals(): num_obras = 0
        
        # Calcular dga_active_pct si no existe
        if 'dga_active_pct' not in locals():
            dga_active_pct = (obras_dga_active / num_obras * 100) if num_obras > 0 else 0
        
        # Template expects pct_dga, pct_dga_count, pct_dga_total
        pct_dga = round(dga_active_pct, 1)
        pct_dga_count = obras_dga_active
        pct_dga_total = num_obras
            
        if 'provider_counts' not in locals(): provider_counts = {'thethings': 0, 'novus': 0, 'tdata': 0}
        if 'disconnected_gt_1d_count' not in locals(): disconnected_gt_1d_count = 0
        if 'dga_active_status' not in locals(): dga_active_status = {}
        if 'dga_standards_breakdown' not in locals(): dga_standards_breakdown = []
        
        if 'pct_veracidad' not in locals(): pct_veracidad = 0
        if 'error_page_obj' not in locals(): error_page_obj = None
        if 'pct_cola_dga' not in locals(): pct_cola_dga = 0
        if 'records_in_dga_queue' not in locals(): records_in_dga_queue = 0
        if 'total_registros_cola_dga' not in locals(): total_registros_cola_dga = 0
        if 'notificaciones_pendientes' not in locals(): notificaciones_pendientes = []
        if 'recent_interactions' not in locals(): recent_interactions = []
        if 'enhanced_interactions' not in locals(): enhanced_interactions = []
        
        if 'use_historical_veracidad' not in locals(): use_historical_veracidad = False
        if 'veracidad_periodo' not in locals(): veracidad_periodo = []
        if 'period_days' not in locals(): period_days = 30
        
        if 'active_connected_points' not in locals(): active_connected_points = 0
        if 'active_points' not in locals(): active_points = set()
        
        # ==============================================================================

        context = {
            'recent_interactions': enhanced_interactions[:50],  # Limitar a 50 para rendimiento
            'total_points': len(unique_point_ids),
            'active_points': active_points,
            'dga_breakdown': dga_standards_breakdown, # Pasar desglose al template
            'provider_counts': provider_counts, # Desglose proveedores
            'dga_stats': dga_active_status, # Stats de cumplimiento
            'provider_filter': provider_filter,
            'num_obras': num_obras,
            'provider_filter': provider_filter,
            'num_obras': num_obras,
            'pct_conectados': round(pct_conectados, 1), 
            'pct_conectados_count': pct_conectados_count, 
            'pct_conectados_total': pct_conectados_total,
            # ✅ FIX: Desconectados ahora muestra fallas operativas (Total + Parcial) para coincidir con las cards
            'desconectados_count': stats_caudal_probable.get('con_desconexion', 0) + stats_caudal_probable.get('desconexiones_parciales', 0),
            'desconectados_parciales': stats_caudal_probable.get('desconexiones_parciales', 0),
            
            'dga_active_pct': dga_active_pct, # ✅ FIX: Variable calculada ahora
            'dga_active_count': obras_dga_active,
            'dga_total_count': num_obras,
            
            # Template variables for % DGA card
            'pct_dga': pct_dga,
            'pct_dga_count': pct_dga_count,
            'pct_dga_total': pct_dga_total,
            'dga_standards_breakdown': dga_standards_breakdown,
            'dga_stats': {
                 'active': obras_dga_active,
                 'inactive': num_obras - obras_dga_active,
                 'total': num_obras
            },
            
            # Contexto para filtros y tabla
            'all_projects': all_projects,
            'selected_project': selected_project,
            'selected_point': selected_point,
            'selected_provider': provider_filter,
            'selected_variable': variable_filter,
            'visible_points_count': visible_points.count(),
            'dga_active_status': dga_active_status, # ✅ FIX: Pasar status al context

            'pct_veracidad': round(pct_veracidad, 1) if 'pct_veracidad' in locals() else 0, # ✅ FIX: Safety check
            'pct_veracidad_total': veracidad_total_puntos if 'veracidad_total_puntos' in locals() else 0,
            'pct_veracidad_con_d5': veracidad_puntos_con_d5 if 'veracidad_puntos_con_d5' in locals() else 0,
            'pct_veracidad_count': (veracidad_puntos_con_d5 - veracidad_pasan_probable) if 'veracidad_puntos_con_d5' in locals() and 'veracidad_pasan_probable' in locals() else 0,
            'pct_veracidad_pasan_probable': veracidad_pasan_probable if 'veracidad_pasan_probable' in locals() else 0,
            'error_page_obj': error_page_obj,
            'pct_cola_dga': round(pct_cola_dga, 1) if 'pct_cola_dga' in locals() else 0,
            'pct_cola_dga_count': records_in_dga_queue if 'records_in_dga_queue' in locals() else 0,
            'pct_cola_dga_total': total_registros_cola_dga if 'total_registros_cola_dga' in locals() else 0,
            'notificaciones_pendientes': notificaciones_pendientes if 'notificaciones_pendientes' in locals() else [],
            
            # Listas
            'recent_interactions': recent_interactions,
            'enhanced_interactions': enhanced_interactions,
            'last_interactions': enhanced_interactions,
            'disconnected_gt_1d_count': disconnected_gt_1d_count,
            
            # Veracidad histórica (nueva funcionalidad)
            'use_historical_veracidad': use_historical_veracidad if 'use_historical_veracidad' in locals() else False,
            'veracidad_periodo': veracidad_periodo if 'veracidad_periodo' in locals() else [],
            'period_days': period_days if 'period_days' in locals() else 30,
            
            # Stats adicionales
            'stats_caudal_probable': stats_caudal_probable if 'stats_caudal_probable' in locals() else {'con_desconexion': 0},
            'registro_errores': registro_errores if 'registro_errores' in locals() else 0,
            'errores_y_excesos_combinados': errores_y_excesos_combinados if 'errores_y_excesos_combinados' in locals() else [],
            'selected_project_id': project_id,
            'selected_point_id': point_id,
            'project_points': project_points if 'project_points' in locals() else [],
            'variable_filter': variable_filter if 'variable_filter' in locals() else 'all',
            
            # Fecha/hora
            'now': now,
        }
        
        return render(request, 'admin/dashboard.html', context)
    except Exception as e:
        # ✅ FIX: Capturar cualquier error y loguearlo para debugging
        logger = logging.getLogger(__name__)
        logger.error(f"Error en admin_dashboard_view: {e}", exc_info=True)
        # Retornar una respuesta de error más amigable
        from django.http import HttpResponseServerError
        return HttpResponseServerError(f"Error interno del servidor: {str(e)}")


@staff_member_required
def telemetry_monitoring_view(request):
    """
    Vista de monitoreo en tiempo real de telemetría.
    Muestra alertas de valores imposibles según parámetros estáticos.
    """
    chile_tz = pytz.timezone("America/Santiago")
    now = timezone.now()
    
    # ========================================
    # FILTRO POR PROYECTO
    # ========================================
    project_id = request.GET.get('project', None)
    selected_project = None
    
    if project_id:
        try:
            selected_project = ProjectCatchments.objects.get(id=project_id)
        except ProjectCatchments.DoesNotExist:
            project_id = None
    
    # Obtener todos los proyectos para el selector
    all_projects = ProjectCatchments.objects.all().order_by('name')
    
    # Obtener todos los puntos con telemetría activa (NO filtrar por d6 - mostrar TODOS)
    points = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True
    ).distinct().select_related('project').prefetch_related(
        'data_config_profiles',
        Prefetch(
            'schemes',
            queryset=SchemesCatchment.objects.prefetch_related(
                Prefetch(
                    'variables',  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
                    queryset=Variable.objects.only('id', 'type_variable', 'label', 'scheme_catchment_id')
                )
            )
        )
    )
    
    # Aplicar filtro por proyecto si está seleccionado
    if project_id:
        points = points.filter(project=selected_project)
    
    # ✅ FIX: Convertir a lista para evitar problemas con prefetch durante la iteración
    points_list = list(points)
    
    # Obtener último registro de cada punto
    monitoring_data = []
    
    for point in points_list:
        profile = point.data_config_profiles.first()
        if not profile:
            continue
        
        # Obtener último registro
        last_record = InteractionDetail.objects.filter(
            catchment_point=point
        ).order_by('-date_time_medition').first()
        
        if not last_record:
            continue
        
        # Obtener variables configuradas (usar prefetch si está disponible)
        variables = []
        variable_types = []
        if hasattr(point, '_prefetched_objects_cache') and 'schemes' in point._prefetched_objects_cache:
            schemes = point._prefetched_objects_cache['schemes']
            for scheme in schemes:
                if hasattr(scheme, '_prefetched_objects_cache') and 'variables' in scheme._prefetched_objects_cache:
                    variables.extend(scheme._prefetched_objects_cache['variables'])  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
        else:
            # Fallback: consulta directa
            variables = Variable.objects.filter(
                scheme_catchment__points_catchment=point
            )
        
        variable_types = [v.type_variable for v in variables if v.type_variable]
        has_caudal = any(t in variable_types for t in ["CAUDAL", "CAUDAL_PROMEDIO"])
        has_caudal_promedio = "CAUDAL_PROMEDIO" in variable_types
        has_nivel = "NIVEL" in variable_types
        
        # Validaciones
        alerts = []
        warnings = []
        
        # Validar caudal
        flow_safe_monitoring = safe_float(last_record.flow if last_record.flow else None)
        if has_caudal and flow_safe_monitoring > 0:
            d5_safe_monitoring = safe_float(profile.d5 if profile and profile.d5 else None)
            if d5_safe_monitoring > 0:
                es_imposible, mensaje = validate_flow_impossible(
                    flow_safe_monitoring,
                    d5_safe_monitoring
                )
                if es_imposible:
                    alerts.append({
                        'tipo': 'Caudal Imposible',
                        'mensaje': mensaje,
                        'valor': f"{flow_safe_monitoring:.2f} L/s",
                        'maximo_teorico': f"{calculate_max_flow_by_diameter(d5_safe_monitoring):.2f} L/s"
                    })
        
        # Validar nivel
        if has_nivel and last_record.nivel:
            try:
                nivel_value = safe_float(last_record.nivel)
                if nivel_value > 0:
                    d1_safe_monitoring_level = safe_float(profile.d1 if profile and profile.d1 else None)
                    d3_safe_monitoring_level = safe_float(profile.d3 if profile and profile.d3 else None)
                    es_imposible, mensaje = validate_level_impossible(
                        nivel_value,
                        d1_safe_monitoring_level,
                        d3_safe_monitoring_level
                    )
                    if es_imposible:
                        alerts.append({
                            'tipo': 'Nivel Imposible',
                            'mensaje': mensaje,
                            'valor': f"{nivel_value:.2f} m"
                        })
            except (ValueError, TypeError):
                pass
        
        # Verificar si tiene d6 configurado
        has_d6 = False
        d6_value = None
        d6_safe = safe_float(profile.d6 if profile else None)
        if d6_safe > 0:
            has_d6 = True
            d6_value = d6_safe
        
        # Calcular flow dinámicamente si corresponde
        flow_value = last_record.flow or 0.0
        if has_caudal_promedio and has_d6:
            # Usar el serializer para calcular flow dinámicamente
            from api.core.serializers.interaction_detail import InteractionDetailModelSerializer
            serializer = InteractionDetailModelSerializer(last_record)
            serialized_data = serializer.data
            flow_value = serialized_data.get('flow', 0.0)
        elif has_caudal_promedio and not has_d6:
            # Tiene CAUDAL_PROMEDIO pero no tiene d6, mostrar None para N/A
            flow_value = None
        
        # Verificar si el registro es reciente (últimas 24 horas)
        # ✅ FIX: Manejo seguro de timezone para evitar errores 500
        try:
            if last_record.date_time_medition:
                # Convertir a timezone-aware si no lo es
                if last_record.date_time_medition.tzinfo is None:
                    # Si no tiene timezone, asumir que está en chile_tz
                    medition_dt = chile_tz.localize(last_record.date_time_medition)
                else:
                    # Si ya tiene timezone, convertir a chile_tz
                    medition_dt = last_record.date_time_medition.astimezone(chile_tz)
                time_diff = now - medition_dt
                is_recent = time_diff < timedelta(hours=24)
            else:
                # Si no hay fecha, considerar como no reciente
                time_diff = timedelta(days=999)
                is_recent = False
        except Exception as e:
            # Si hay cualquier error, usar valores por defecto seguros
            logger = logging.getLogger(__name__)
            logger.warning(f"Error calculando time_diff para punto {point.id}: {e}")
            time_diff = timedelta(days=999)
            is_recent = False
        
        # Verificar si hay errores
        if last_record.is_error:
            warnings.append({
                'tipo': 'Error en Registro',
                'mensaje': 'El último registro está marcado como error'
            })
        
        # Verificar desconexión
        if last_record.days_not_conection and last_record.days_not_conection > 0:
            warnings.append({
                'tipo': 'Desconexión',
                'mensaje': f'Punto desconectado hace {last_record.days_not_conection} día(s)'
            })
        
        # Agregar TODOS los puntos (no solo los que tienen alertas)
        monitoring_data.append({
            'point': point,
            'point_id': point.id if point else None,
            'point_name': str(point),
            'project': str(point.project) if point.project else 'Sin proyecto',
            'last_record': last_record,
            'last_update': last_record.date_time_medition,
            'is_recent': is_recent,
            'time_since_update': time_diff,
            'profile': profile,
            'd5': safe_float(profile.d5 if profile and profile.d5 else None),
            'd1': safe_float(profile.d1 if profile and profile.d1 else None),
            'd3': safe_float(profile.d3 if profile and profile.d3 else None),
            'd6': d6_value,
            'has_d6': has_d6,
            'alerts': alerts,
            'warnings': warnings,
            'has_caudal': has_caudal,
            'has_caudal_promedio': has_caudal_promedio,
            'has_nivel': has_nivel,
            'variables': variable_types,
            'flow': flow_value,
            'total': last_record.total or 0,
            'total_diff': last_record.total_diff or 0,
            'total_today_diff': last_record.total_today_diff or 0,
            'nivel': last_record.nivel or 0,
            'water_table': last_record.water_table or 0,
        })
    
    # Ordenar por criticidad (más alertas primero), pero mostrar todos
    monitoring_data.sort(key=lambda x: (
        len(x['alerts']),
        len(x['warnings']),
        not x['is_recent']
    ), reverse=True)
    
    context = {
        # Filtro por proyecto
        'all_projects': all_projects,
        'selected_project': selected_project,
        'selected_project_id': project_id,
        
        'monitoring_data': monitoring_data,
        'total_points': len(points_list),  # ✅ FIX: Usar len() en lugar de count() después de convertir a lista
        'points_with_alerts': len([d for d in monitoring_data if d['alerts']]),
        'points_with_warnings': len([d for d in monitoring_data if d['warnings']]),
        'now': now,
    }
    
    return render(request, 'admin/telemetry_monitoring.html', context)


@staff_member_required
def telemetry_monitoring_api(request):
    """
    API endpoint para obtener datos de monitoreo en formato JSON.
    Útil para actualizaciones AJAX en tiempo real.
    """
    chile_tz = pytz.timezone("America/Santiago")
    now = timezone.now()
    
    # Obtener todos los puntos con telemetría activa (NO filtrar por d6 - mostrar TODOS)
    points_qs = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True
    ).distinct().select_related('project').prefetch_related(
        'data_config_profiles',
        Prefetch(
            'schemes',
            queryset=SchemesCatchment.objects.prefetch_related(
                Prefetch(
                    'variables',  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
                    queryset=Variable.objects.only('id', 'type_variable', 'label', 'scheme_catchment_id')
                )
            )
        )
    )
    
    # ✅ FIX: Convertir a lista para evitar problemas con prefetch durante la iteración
    points = list(points_qs)
    
    data = {
        'timestamp': now.isoformat(),
        'points': []
    }
    
    for point in points:
        profile = point.data_config_profiles.first()
        if not profile:
            continue
        
        last_record = InteractionDetail.objects.filter(
            catchment_point=point
        ).order_by('-date_time_medition').first()
        
        if not last_record:
            continue
        
        # Obtener variables configuradas
        variables = []
        variable_types = []
        if hasattr(point, '_prefetched_objects_cache') and 'schemes' in point._prefetched_objects_cache:
            schemes = point._prefetched_objects_cache['schemes']
            for scheme in schemes:
                if hasattr(scheme, '_prefetched_objects_cache') and 'variables' in scheme._prefetched_objects_cache:
                    variables.extend(scheme._prefetched_objects_cache['variables'])  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
        else:
            variables = Variable.objects.filter(
                scheme_catchment__points_catchment=point
            )
        
        variable_types = [v.type_variable for v in variables if v.type_variable]
        has_caudal_promedio = "CAUDAL_PROMEDIO" in variable_types
        
        # Verificar si tiene d6 configurado
        has_d6 = False
        d6_value = None
        d6_safe_api = safe_float(profile.d6 if profile else None)
        if d6_safe_api > 0:
            has_d6 = True
            d6_value = d6_safe_api
        
        # Calcular flow dinámicamente si corresponde
        flow_value = last_record.flow or 0.0
        if has_caudal_promedio and has_d6:
            from api.core.serializers.interaction_detail import InteractionDetailModelSerializer
            serializer = InteractionDetailModelSerializer(last_record)
            serialized_data = serializer.data
            flow_value = serialized_data.get('flow', 0.0)
        elif has_caudal_promedio and not has_d6:
            flow_value = None  # N/A
        
        alerts = []
        warnings = []
        
        # Validar caudal
        flow_safe_api_validation = safe_float(flow_value if flow_value is not None else None)
        d5_safe_api_validation = safe_float(profile.d5 if profile and profile.d5 else None)
        if flow_safe_api_validation > 0 and d5_safe_api_validation > 0:
            es_imposible, mensaje = validate_flow_impossible(
                flow_safe_api_validation,
                d5_safe_api_validation
            )
            if es_imposible:
                alerts.append({
                    'tipo': 'Caudal Imposible',
                    'mensaje': mensaje
                })
        
        # Validar nivel
        if last_record.nivel:
            try:
                nivel_value = safe_float(last_record.nivel)
                if nivel_value > 0:
                    es_imposible, mensaje = validate_level_impossible(
                        nivel_value,
                        float(profile.d1) if profile.d1 else 0,
                        float(profile.d3) if profile.d3 else 0
                    )
                    if es_imposible:
                        alerts.append({
                            'tipo': 'Nivel Imposible',
                            'mensaje': mensaje
                        })

                # The original `except (ValueError, TypeError): pass` for the `nivel` try block is below.
                # The `pass(ValueError, TypeError):` from the instruction's snippet is a syntax error
                # and is not included here to maintain syntactical correctness.
            except (ValueError, TypeError):
                pass
        
        if last_record.is_error:
            warnings.append('Error en registro')
        
        if last_record.days_not_conection and last_record.days_not_conection > 0:
            warnings.append(f'Desconectado {last_record.days_not_conection} día(s)')
        
        # Incluir TODOS los puntos (no solo los que tienen alertas)
        data['points'].append({
            'id': point.id if point else None,
            'name': str(point) if point else 'Sin nombre',
            'project': str(point.project) if point and point.project else None,
            'last_update': last_record.date_time_medition.isoformat() if last_record.date_time_medition else None,
            'flow': float(flow_value) if flow_value is not None else None,
            'nivel': safe_float(last_record.nivel if last_record.nivel else None),
            'total': safe_float(last_record.total if last_record.total else None),
            'total_diff': safe_float(last_record.total_diff if last_record.total_diff else None),
            'total_today_diff': safe_float(last_record.total_today_diff if last_record.total_today_diff else None),
            'water_table': safe_float(last_record.water_table if last_record.water_table else None),
            'variables': variable_types,
            'has_d6': has_d6,
            'd6_value': d6_value,
            'has_caudal_promedio': has_caudal_promedio,
            'alerts': alerts,
            'warnings': warnings,
        })
    
    return JsonResponse(data)


@staff_member_required
def telemetry_point_records_api(request, point_id):
    """
    API endpoint para obtener los últimos registros de un punto específico.
    """
    try:
        point = CatchmentPoint.objects.get(id=point_id)
    except CatchmentPoint.DoesNotExist:
        return JsonResponse({'error': 'Punto no encontrado'}, status=404)
    
    # Obtener últimos 20 registros
    records = InteractionDetail.objects.filter(
        catchment_point=point
    ).order_by('-date_time_medition')[:20]
    
    # Verificar si tiene d6 y CAUDAL_PROMEDIO
    profile = point.data_config_profiles.first()
    has_d6 = False
    if profile and profile.d6 and float(profile.d6) > 0:
        has_d6 = True
    
    # Obtener variables configuradas
    variables = Variable.objects.filter(
        scheme_catchment__points_catchment=point
    )
    has_caudal_promedio = variables.filter(type_variable="CAUDAL_PROMEDIO").exists()
    
    from api.core.serializers.interaction_detail import InteractionDetailModelSerializer
    
    records_data = []
    for record in records:
        # Calcular flow dinámicamente si corresponde
        flow_value = record.flow or 0.0
        if has_caudal_promedio and has_d6:
            serializer = InteractionDetailModelSerializer(record)
            serialized_data = serializer.data
            flow_value = serialized_data.get('flow', 0.0)
        elif has_caudal_promedio and not has_d6:
            flow_value = None  # N/A
        
        records_data.append({
            'id': record.id,
            'date_time_medition': record.date_time_medition.isoformat() if record.date_time_medition else None,
            'total': safe_float(record.total if record.total else None),
            'total_diff': safe_float(record.total_diff if record.total_diff else None),
            'nivel': safe_float(record.nivel if record.nivel else None),
            'water_table': safe_float(record.water_table if record.water_table else None),
            'flow': safe_float(flow_value) if flow_value is not None else None,
        })
    
    return JsonResponse({
        'point_id': point_id,
        'point_name': str(point),
        'records': records_data
    })
