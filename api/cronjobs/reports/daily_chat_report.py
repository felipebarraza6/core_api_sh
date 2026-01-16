"""
Reporte Diario Google Chat - Telemetría
========================================
Envío: 09:00 AM Chile (12:00 UTC)

Contenido:
1. Desconectados (ordenados por días DESC)
2. Alertas con contexto de esquema:
   - Nivel=0/NULL solo si esquema tiene NIVEL
   - Caudal imposible/NULL solo si esquema tiene CAUDAL
3. Reinicios del día (total_diff < 0)
4. Top 5 caudales más altos
"""

import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Min, Max
from django_redis import get_redis_connection
from api.core.models import CatchmentPoint, InteractionDetail, SchemesCatchment, Variable
from api.core.utils.google_chat import send_google_chat_message
from api.cronjobs.reports.daily_bulletin import get_disconnected_points

logger = logging.getLogger(__name__)


def get_points_with_variable(variable_type):
    """
    Retorna IDs de puntos que tienen una variable del tipo especificado en su esquema.
    """
    # Buscar esquemas que tienen esta variable
    scheme_ids = Variable.objects.filter(
        type_variable=variable_type
    ).values_list('scheme_catchment_id', flat=True).distinct()
    
    # Buscar puntos que usan estos esquemas
    point_ids = set()
    for scheme_id in scheme_ids:
        try:
            scheme = SchemesCatchment.objects.get(id=scheme_id)
            for point in scheme.points_catchment.all():
                point_ids.add(point.id)
        except SchemesCatchment.DoesNotExist:
            pass
    
    return point_ids


def get_critical_alerts_with_schema():
    """
    Alertas críticas CON CONTEXTO DE ESQUEMA:
    - Nivel=0 solo para puntos con variable NIVEL
    - Reinicios (total_diff < 0)
    Ventana de tiempo: 9AM ayer a 9AM hoy
    Retorna: (alerts dict, start_time, end_time)
    """
    import pytz
    chile = pytz.timezone("America/Santiago")
    now_chile = timezone.now().astimezone(chile)
    
    # 9 AM de hoy
    today_9am = now_chile.replace(hour=9, minute=0, second=0, microsecond=0)
    # Si aún no son las 9 AM, usar 9 AM de ayer como fin
    if now_chile.hour < 9:
        end_time = today_9am - timedelta(days=1)
    else:
        end_time = today_9am
    # Inicio: 24 horas antes del fin
    start_time = end_time - timedelta(hours=24)
    
    alerts = {
        'nivel_zero': [],
        'resets': [],
        'top_flows': [],
        'start_time': start_time,
        'end_time': end_time
    }
    
    # Obtener puntos por tipo de variable
    points_with_nivel = get_points_with_variable('NIVEL')
    
    # 1. NIVEL = 0 (solo puntos con variable NIVEL)
    if points_with_nivel:
        nivel_zero = InteractionDetail.objects.filter(
            date_time_medition__gte=start_time,
            date_time_medition__lte=end_time,
            catchment_point_id__in=points_with_nivel
        ).values('catchment_point_id').annotate(
            total_records=Count('id'),
            max_nivel=Max('nivel'),
            min_nivel=Min('nivel')
        ).filter(
            max_nivel=0,
            min_nivel=0,
            total_records__gte=12
        )
        
        for item in nivel_zero:
            alerts['nivel_zero'].append({
                'point_id': item['catchment_point_id'],
                'records': item['total_records']
            })
    
    # 2. REINICIOS - Detectar cuando total actual < total anterior (reinicio de logger)
    # Buscar puntos activos en el período
    
    # Obtener puntos únicos con registros en el período
    active_point_ids = InteractionDetail.objects.filter(
        date_time_medition__gte=start_time,
        date_time_medition__lte=end_time,
        total__isnull=False
    ).values_list('catchment_point_id', flat=True).distinct()
    
    reset_points = {}
    for pid in active_point_ids:
        records = list(InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gte=start_time,
            date_time_medition__lte=end_time,
            total__isnull=False
        ).order_by('date_time_medition').values('total', 'date_time_medition'))
        
        if len(records) < 2:
            continue
        
        resets_info = []
        prev_total = None
        for r in records:
            try:
                curr = float(r['total']) if r['total'] else 0
                if prev_total is not None and curr < prev_total - 10:  # Tolerancia de 10
                    resets_info.append({
                        'before': prev_total,
                        'after': curr
                    })
                prev_total = curr
            except:
                pass
        
        if resets_info:
            # Guardar el último reinicio (el más reciente)
            last_reset = resets_info[-1]
            reset_points[pid] = {
                'count': len(resets_info),
                'before': last_reset['before'],
                'after': last_reset['after']
            }
    
    for pid, info in reset_points.items():
        alerts['resets'].append({
            'point_id': pid,
            'count': info['count'],
            'before': info['before'],
            'after': info['after']
        })
    
    # 3. TOP 5 CAUDALES MÁS ALTOS (con fecha/hora y proyecto)
    # Primero obtener los 5 puntos con mayor flow
    top_5_points = InteractionDetail.objects.filter(
        date_time_medition__gte=start_time,
        date_time_medition__lte=end_time,
        flow__isnull=False,
        flow__gt=0
    ).values('catchment_point_id').annotate(
        max_flow=Max('flow')
    ).order_by('-max_flow')[:5]
    
    # Para cada punto, obtener el registro con el max flow (para tener el timestamp)
    for item in top_5_points:
        record = InteractionDetail.objects.filter(
            catchment_point_id=item['catchment_point_id'],
            date_time_medition__gte=start_time,
            date_time_medition__lte=end_time,
            flow=item['max_flow']
        ).first()
        
        if record:
            alerts['top_flows'].append({
                'point_id': item['catchment_point_id'],
                'max_flow': item['max_flow'],
                'timestamp': record.date_time_medition
            })
    
    # Enriquecer con info del punto
    all_point_ids = set()
    list_keys = ['nivel_zero', 'resets', 'top_flows']
    for key in list_keys:
        for a in alerts[key]:
            all_point_ids.add(a['point_id'])
    
    points = {p.id: p for p in CatchmentPoint.objects.filter(
        id__in=all_point_ids
    ).select_related('project__client')}
    
    def enrich(alert):
        p = points.get(alert['point_id'])
        if p:
            alert['title'] = p.title
            alert['client'] = p.project.client.name if (p.project and p.project.client) else "N/A"
        return alert
    
    for key in list_keys:
        alerts[key] = [enrich(a) for a in alerts[key]]
    
    return alerts


def get_error_details():
    """Obtiene errores de sistema del día CON el mensaje de error."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    errors = []
    
    try:
        con = get_redis_connection("default")
        daily_errors_key = f"daily_errors:{today_str}"
        error_point_ids = con.smembers(daily_errors_key)
        
        for pid_bytes in error_point_ids:
            pid = int(pid_bytes)
            error_key = f"error_detail:{pid}:{today_str}"
            error_msg = con.get(error_key)
            
            if error_msg:
                error_msg = error_msg.decode('utf-8') if isinstance(error_msg, bytes) else str(error_msg)
            else:
                error_msg = "Error no especificado"
            
            errors.append({'point_id': pid, 'error': error_msg})
            
    except Exception as e:
        logger.error(f"Error leyendo errores de Redis: {e}")
        return []
    
    if not errors:
        return []
    
    point_ids = [e['point_id'] for e in errors]
    points = {p.id: p for p in CatchmentPoint.objects.filter(
        id__in=point_ids
    ).select_related('project__client')}
    
    results = []
    for err in errors:
        p = points.get(err['point_id'])
        if p:
            c_name = p.project.client.name if (p.project and p.project.client) else "N/A"
            results.append({
                'title': p.title,
                'client': c_name,
                'error': err['error']
            })
    
    return results


def run():
    """
    Reporte Diario Google Chat (09:00 AM Chile):
    1. Desconectados (ordenados por días)
    2. Alertas con contexto de esquema
    3. Reinicios
    4. Top 5 caudales
    """
    logger.info("Iniciando Reporte Diario Google Chat...")
    
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 1. Desconectados
        all_disconnected = get_disconnected_points()
        disconnected = [d for d in all_disconnected if d.get('days_disconnected', 0) >= 1]
        disconnected = sorted(disconnected, key=lambda x: x.get('days_disconnected', 0), reverse=True)
        
        new_disconnected = [d for d in disconnected if d.get('days_disconnected', 0) <= 2]
        old_disconnected = [d for d in disconnected if d.get('days_disconnected', 0) > 2]
        
        # 2. Alertas con contexto
        alerts = get_critical_alerts_with_schema()
        
        # 3. Errores de sistema
        system_errors = get_error_details()
        
        # ============================================================
        # CONSTRUIR MENSAJE
        # ============================================================
        import pytz
        chile = pytz.timezone("America/Santiago")
        
        # Formatear fechas para el header
        start_dt = alerts['start_time'].astimezone(chile)
        end_dt = alerts['end_time'].astimezone(chile)
        start_str = start_dt.strftime("%d/%m %H:%M")
        end_str = end_dt.strftime("%d/%m %H:%M")
        
        msg_parts = [f"📊 **REPORTE DIARIO DE TELEMETRÍA**"]
        msg_parts.append(f"📅 Desde {start_str} hasta {end_str}")
        
        msg_parts.append(f"\n📈 **Resumen:** {len(disconnected)} desconectados | {len(new_disconnected)} nuevos | {len(alerts['resets'])} reinicios")
        
        # --- NUEVAS DESCONEXIONES ---
        if new_disconnected:
            msg_parts.append(f"\n🆕 **Nuevas Desconexiones ({len(new_disconnected)}):**")
            for d in new_disconnected:
                msg_parts.append(f"- ⚡ {d['title']} ({d['client']}): {d['days_disconnected']} día(s)")
        
        # --- DESCONECTADOS ANTIGUOS ---
        if old_disconnected:
            msg_parts.append(f"\n🔌 **Desconectados Antiguos ({len(old_disconnected)}):**")
            for d in old_disconnected:
                msg_parts.append(f"- {d['title']} ({d['client']}): {d['days_disconnected']} días")
        
        if not disconnected:
            msg_parts.append("\n✅ **Todos los puntos conectados**")
        
        # --- REINICIOS HOY ---
        if alerts['resets']:
            msg_parts.append(f"\n🔄 **Reinicios ({len(alerts['resets'])}):**")
            for a in alerts['resets']:
                before = int(a.get('before', 0))
                after = int(a.get('after', 0))
                msg_str = f"- {a.get('title', 'N/A')} ({a.get('client', 'N/A')}): {before:,} → {after:,} m³"
                if after < 0:
                    msg_str += " ⚠️ (Valor negativo/Error)"
                msg_parts.append(msg_str)
        
        # --- NIVEL = 0 (solo si tienen variable NIVEL) ---
        if alerts['nivel_zero']:
            msg_parts.append(f"\n📉 **Nivel = 0 ({len(alerts['nivel_zero'])}):**")
            for a in alerts['nivel_zero']:
                msg_parts.append(f"- {a.get('title', 'N/A')} ({a.get('client', 'N/A')})")
        
        # --- TOP 5 CAUDALES ---
        if alerts['top_flows']:
            msg_parts.append(f"\n🏆 **Top 5 Caudales Más Altos:**")
            for i, a in enumerate(alerts['top_flows'], 1):
                ts = a.get('timestamp')
                ts_str = ts.astimezone(chile).strftime("%d/%m %H:%M") if ts else "N/A"
                msg_parts.append(f"- {i}. {a.get('title', 'N/A')} ({a.get('client', 'N/A')}): {a['max_flow']:.1f} L/s @ {ts_str}")
        
        # --- ERRORES DE SISTEMA (solo si hay) ---
        if system_errors:
            msg_parts.append(f"\n🛠️ **Errores de Sistema ({len(system_errors)}):**")
            for err in system_errors:
                error_short = err['error'][:80] + "..." if len(err['error']) > 80 else err['error']
                msg_parts.append(f"- {err['title']}: {error_short}")
        
        # ============================================================
        # ENVIAR
        # ============================================================
        full_msg = "\n".join(msg_parts)
        
        if len(full_msg) > 4000:
            parts = [full_msg[i:i+4000] for i in range(0, len(full_msg), 4000)]
            for p in parts:
                send_google_chat_message(p)
        else:
            send_google_chat_message(full_msg)
        
        logger.info("Reporte Diario Google Chat enviado.")
        
    except Exception as e:
        logger.error(f"Error global en Reporte Diario Chat: {e}", exc_info=True)
