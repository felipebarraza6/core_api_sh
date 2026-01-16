"""Boletín Diario de Telemetría - Cronjob"""

import logging
import re
import pytz
from datetime import timedelta
from collections import defaultdict
from django.utils import timezone
from django.conf import settings
from django.db.models import Q

from api.core.models import (
    CatchmentPoint, 
    InteractionDetail, 
    ProfileDataConfigCatchment,
    NotificationsCatchment,
    DgaDataConfigCatchment,
    User
)

logger = logging.getLogger(__name__)

# Zona horaria Chile
CHILE_TZ = pytz.timezone('America/Santiago')

# Configuración de destinatarios adicionales
ADDITIONAL_RECIPIENTS = []

# Nombres en español
DIAS_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
MESES_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

# Orden de estándares para ordenamiento
STANDARD_ORDER = {'MAYOR': 1, 'MEDIO': 2, 'MENOR': 3, 'CAUDALES_MUY_PEQUENOS': 4, 'SIN_ESTANDAR': 5, 'FORMULARIO': 6}


def to_chile_tz(dt):
    """Convertir datetime a hora Chile"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(CHILE_TZ)


def format_dt_chile(dt, fmt='%d/%m/%y %H:%M'):
    """Formatear datetime a string en hora Chile con año"""
    if dt is None:
        return 'N/A'
    chile_dt = to_chile_tz(dt)
    return chile_dt.strftime(fmt)


def format_date_spanish(dt):
    """Formatear fecha en español con hora Chile"""
    chile_dt = to_chile_tz(dt)
    day_name = DIAS_ES[chile_dt.weekday()]
    month_name = MESES_ES[chile_dt.month - 1]
    return f"{day_name} {chile_dt.day} de {month_name}, {chile_dt.year} - {chile_dt.strftime('%H:%M')} hrs (Hora Chile)"


def format_number(num):
    """Formatear número con punto como separador de miles"""
    if num is None:
        return "0"
    try:
        val = float(num)
        return f"{int(val):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"


def get_standard_order(standard):
    """Obtener orden numérico del estándar para ordenamiento"""
    return STANDARD_ORDER.get(standard, 99)


def get_staff_emails():
    """Obtener emails de usuarios staff/admin"""
    return list(
        User.objects.filter(
            Q(is_staff=True) | Q(is_superuser=True),
            email__isnull=False
        ).exclude(email='').values_list('email', flat=True)
    )


def get_health_summary(exclude_ids=None):
    """Obtener resumen de salud del sistema"""
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    
    total_active = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True
    ).count()
    
    query = InteractionDetail.objects.filter(
        date_time_medition__gte=last_24h
    )
    
    if exclude_ids:
        query = query.exclude(catchment_point_id__in=exclude_ids)
    
    points_with_data = query.values('catchment_point_id').distinct().count()
    
    total_measurements = InteractionDetail.objects.filter(
        date_time_medition__gte=last_24h
    ).count()
    
    health_pct = (points_with_data / total_active * 100) if total_active else 0
    
    return {
        'total_active': total_active,
        'points_with_data': points_with_data,
        'points_without_data': total_active - points_with_data,
        'total_measurements': total_measurements,
        'health_pct': round(health_pct, 1)
    }


def get_disconnected_points():
    """Obtener puntos desconectados + formularios sin datos"""
    all_active = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True
    ).select_related('project__client')
    
    disconnected = []
    for point in all_active:
        last = InteractionDetail.objects.filter(
            catchment_point_id=point.id
        ).order_by('-date_time_medition').first()
        
        # Obtener config DGA
        dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=point.id).first()
        code_dga = dga_config.code_dga if dga_config and dga_config.code_dga else ''
        standard = dga_config.standard if dga_config else 'SIN_ESTANDAR'
        
        client = point.project.client.name if point.project and point.project.client else 'N/A'
        
        # Determinar proveedor (nombres actualizados)
        if point.is_tdata:
            proveedor = 'Twin'
        elif point.is_novus:
            proveedor = 'Novus'
        elif point.is_thethings:
            proveedor = 'Nettra'
        else:
            proveedor = 'N/A'
        
        # Desconectado si days_not_conection > 0
        if last and last.days_not_conection and last.days_not_conection > 0:
            # Buscar última medición cuando estaba conectado usando la fecha del logger
            last_connected = None
            if last.date_time_last_logger:
                last_connected = InteractionDetail.objects.filter(
                    catchment_point_id=point.id,
                    date_time_medition=last.date_time_last_logger
                ).first()
                
                # Fallback 1: si no encuentra exacto, buscar el más cercano anterior a la fecha del logger
                if not last_connected:
                    last_connected = InteractionDetail.objects.filter(
                        catchment_point_id=point.id,
                        date_time_medition__lte=last.date_time_last_logger
                    ).order_by('-date_time_medition').first()
            
            # Fallback 2: Si aún no encuentra (o no había fecha logger), buscar el último registro conectado
            if not last_connected:
                last_connected = InteractionDetail.objects.filter(
                    catchment_point_id=point.id,
                    days_not_conection=0
                ).order_by('-date_time_medition').first()
            
            last_connected_date = format_dt_chile(last_connected.date_time_medition) if last_connected else 'N/A'
            
            # Valores última conexión válida
            conn_total = last_connected.total or 0 if last_connected else 0
            conn_flow = last_connected.flow or 0 if last_connected else 0
            conn_nivel = last_connected.nivel or 0 if last_connected else 0
            
            # Valores última medición
            last_total = last.total or 0
            last_flow = last.flow or 0
            last_nivel = last.nivel or 0
            
            disconnected.append({
                'id': point.id,
                'title': point.title or 'Sin nombre',
                'client': client,
                'code_dga': code_dga,
                'standard': standard,
                'proveedor': proveedor,
                'last_date': format_dt_chile(last.date_time_medition),
                'last_connected_date': last_connected_date,
                'days_disconnected': last.days_not_conection,
                'conn_total': conn_total,
                'conn_flow': conn_flow,
                'conn_nivel': conn_nivel,
                'last_total': last_total,
                'last_flow': last_flow,
                'last_nivel': last_nivel,
                'is_formulario': False
            })
        # También incluir FORMULARIOS sin ningún dato
        elif not last and standard == 'FORMULARIO':
            disconnected.append({
                'id': point.id,
                'title': point.title or 'Sin nombre',
                'client': client,
                'code_dga': code_dga,
                'standard': 'FORMULARIO',
                'proveedor': proveedor,
                'last_date': 'Sin datos',
                'logger_date': 'N/A',
                'last_connected_date': 'N/A',
                'days_disconnected': 999,
                'conn_total': 0,
                'conn_flow': 0,
                'conn_nivel': 0,
                'last_total': 0,
                'last_flow': 0,
                'last_nivel': 0,
                'is_formulario': True
            })
    
    # Ordenar: primero por código de obra (los que tienen), luego por estándar
    def sort_key(x):
        has_code = 0 if x['code_dga'] else 1
        std_order = get_standard_order(x['standard'])
        return (has_code, std_order, -x['days_disconnected'])
    
    return sorted(disconnected, key=sort_key)


def get_stuck_points():
    """Obtener puntos sin variación en más de 24 horas"""
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    
    stuck = []
    
    points = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True
    ).select_related('project__client')
    
    for point in points:
        records = list(InteractionDetail.objects.filter(
            catchment_point_id=point.id,
            date_time_medition__gte=last_24h
        ).values_list('total_diff', flat=True))
        
        # Si tiene al menos 12 registros (1 por hora = 12h mínimo)
        if len(records) >= 12:
            all_zero = all(d == 0 or d is None for d in records)
            if all_zero:
                # Obtener config DGA
                dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=point.id).first()
                code_dga = dga_config.code_dga if dga_config and dga_config.code_dga else ''
                standard = dga_config.standard if dga_config else 'SIN_ESTANDAR'
                
                client = point.project.client.name if point.project and point.project.client else 'N/A'
                
                # Proveedor
                if point.is_tdata:
                    proveedor = 'Twin'
                elif point.is_novus:
                    proveedor = 'Novus'
                elif point.is_thethings:
                    proveedor = 'Nettra'
                else:
                    proveedor = 'N/A'
                
                # Última medición
                last = InteractionDetail.objects.filter(
                    catchment_point_id=point.id
                ).order_by('-date_time_medition').first()
                
                last_date = last.date_time_medition.strftime('%d/%m %H:%M') if last and last.date_time_medition else 'N/A'
                
                # Última variación (cuando total_diff > 0)
                last_variation = InteractionDetail.objects.filter(
                    catchment_point_id=point.id,
                    total_diff__gt=0
                ).order_by('-date_time_medition').first()
                
                last_variation_date = format_dt_chile(last_variation.date_time_medition) if last_variation else 'N/A'
                
                # Valores última variación
                var_total = last_variation.total or 0 if last_variation else 0
                var_flow = last_variation.flow or 0 if last_variation else 0
                var_nivel = last_variation.nivel or 0 if last_variation else 0
                
                # Valores última medición
                last_total = last.total or 0 if last else 0
                last_flow = last.flow or 0 if last else 0
                last_nivel = last.nivel or 0 if last else 0
                
                stuck.append({
                    'id': point.id,
                    'title': point.title or 'Sin nombre',
                    'client': client,
                    'code_dga': code_dga,
                    'standard': standard,
                    'proveedor': proveedor,
                    'last_date': format_dt_chile(last.date_time_medition) if last else 'N/A',
                    'last_variation_date': last_variation_date,
                    'hours_stuck': len(records),
                    'var_total': var_total,
                    'var_flow': var_flow,
                    'var_nivel': var_nivel,
                    'last_total': last_total,
                    'last_flow': last_flow,
                    'last_nivel': last_nivel
                })
    
    # Ordenar por código de obra y estándar y horas pegado descendente
    def sort_key(x):
        has_code = 0 if x['code_dga'] else 1
        std_order = get_standard_order(x['standard'])
        return (has_code, std_order, -x['hours_stuck'])
    
    return sorted(stuck, key=sort_key)


def get_recent_resets_summary():
    """Obtener resumen + últimos 5 resets por punto con detalle"""
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    
    resets = NotificationsCatchment.objects.filter(
        title__icontains='Reinicio',
        created__gte=last_24h
    ).select_related('point_catchment__project__client').order_by('-created')
    
    # Agrupar por punto con últimos 5 eventos
    grouped = defaultdict(lambda: {'count': 0, 'client': '', 'title': '', 'events': []})
    
    for r in resets:
        if r.point_catchment:
            pid = r.point_catchment.id
            grouped[pid]['count'] += 1
            grouped[pid]['title'] = r.point_catchment.title or 'Sin nombre'
            grouped[pid]['client'] = r.point_catchment.project.client.name if r.point_catchment.project and r.point_catchment.project.client else 'N/A'
            
            # Guardar hasta 5 eventos con detalle
            if len(grouped[pid]['events']) < 5 and r.message:
                match = re.search(r'Valor anterior: (\d+), Valor actual: (\d+)', r.message)
                if match:
                    grouped[pid]['events'].append({
                        'date': r.created.strftime('%d/%m %H:%M'),
                        'val_anterior': int(match.group(1)),
                        'val_actual': int(match.group(2))
                    })
    
    result = []
    for pid, data in grouped.items():
        dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=pid).first()
        code_dga = dga_config.code_dga if dga_config and dga_config.code_dga else ''
        
        result.append({
            'id': pid,
            'title': data['title'],
            'client': data['client'],
            'code_dga': code_dga,
            'count': data['count'],
            'events': data['events'],
            'is_critical': data['count'] > 5
        })
    
    return sorted(result, key=lambda x: -x['count'])


def get_points_with_addition():
    """Obtener puntos con constante por reinicio"""
    profiles = ProfileDataConfigCatchment.objects.filter(
        addition__gt=0
    ).select_related('point_catchment__project__client')
    
    result = []
    for p in profiles:
        if p.point_catchment:
            # Obtener config DGA
            dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=p.point_catchment.id).first()
            code_dga = dga_config.code_dga if dga_config and dga_config.code_dga else ''
            standard = dga_config.standard if dga_config else 'SIN_ESTANDAR'
            
            # Obtener último registro para ver valores
            last = InteractionDetail.objects.filter(
                catchment_point_id=p.point_catchment.id
            ).order_by('-date_time_medition').first()
            
            last_total = last.total if last else 0
            
            client = p.point_catchment.project.client.name if p.point_catchment.project and p.point_catchment.project.client else 'N/A'
            result.append({
                'id': p.point_catchment.id,
                'title': p.point_catchment.title or 'Sin nombre',
                'client': client,
                'code_dga': code_dga,
                'standard': standard,
                'addition': p.addition,
                'last_total': last_total
            })
    
    return result


def get_formularios_sin_datos():
    """Obtener puntos con estándar FORMULARIO que no tienen ningún dato"""
    from api.core.models import DgaDataConfigCatchment
    
    formularios = DgaDataConfigCatchment.objects.filter(
        standard='FORMULARIO'
    ).select_related('point_catchment__project__client')
    
    result = []
    for f in formularios:
        if f.point_catchment:
            has_data = InteractionDetail.objects.filter(catchment_point_id=f.point_catchment.id).exists()
            if not has_data:
                client = f.point_catchment.project.client.name if f.point_catchment.project and f.point_catchment.project.client else 'N/A'
                result.append({
                    'id': f.point_catchment.id,
                    'title': f.point_catchment.title or 'Sin nombre',
                    'client': client,
                    'code_dga': f.code_dga or ''
                })
    
    return result


def generate_html_bulletin(data):
    """Generar HTML del boletín"""
    now = timezone.now()
    fecha_es = format_date_spanish(now)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
            .container {{ max-width: 900px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #1F3461 0%, #2d4a7c 100%); color: white; padding: 25px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 24px; }}
            .header p {{ margin: 5px 0 0; opacity: 0.8; font-size: 14px; }}
            .content {{ padding: 25px; }}
            .health-box {{ background: linear-gradient(135deg, #52c41a 0%, #73d13d 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px; }}
            .health-box .big {{ font-size: 48px; font-weight: bold; }}
            .health-box .label {{ font-size: 14px; opacity: 0.9; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 25px; }}
            .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }}
            .stat-card .number {{ font-size: 28px; font-weight: bold; color: #1F3461; }}
            .stat-card .label {{ font-size: 12px; color: #666; }}
            .section {{ margin-bottom: 25px; }}
            .section-title {{ font-size: 16px; font-weight: bold; color: #1F3461; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 2px solid #eee; }}
            .section-count {{ font-size: 12px; color: #888; font-weight: normal; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
            th {{ background: #f0f2f5; padding: 6px; text-align: left; font-weight: 600; }}
            td {{ padding: 6px; border-bottom: 1px solid #eee; }}
            .badge-red {{ background: #ff4d4f; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; }}
            .badge-yellow {{ background: #faad14; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; }}
            .badge-blue {{ background: #1890ff; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; }}
            .badge-critical {{ background: #a8071a; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }}
            .badge-std {{ background: #722ed1; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; }}
            .footer {{ background: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #888; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 Boletín Diario de Telemetría</h1>
                <p>{fecha_es}</p>
            </div>
            
            <div class="content">
                <div class="health-box">
                    <div class="big">{data['health']['health_pct']}%</div>
                    <div class="label">SALUD GENERAL DEL SISTEMA</div>
                </div>
                
                <!-- Stats en tabla para compatibilidad con email -->
                <table style="width:100%;margin-bottom:25px;border-collapse:collapse;">
                    <tr>
                        <td style="width:33%;text-align:center;background:#f8f9fa;padding:15px;border-radius:8px;">
                            <div style="font-size:28px;font-weight:bold;color:#1F3461;">{data['health']['total_active']}</div>
                            <div style="font-size:12px;color:#666;">Puntos Activos</div>
                        </td>
                        <td style="width:5%;"></td>
                        <td style="width:33%;text-align:center;background:#f8f9fa;padding:15px;border-radius:8px;">
                            <div style="font-size:28px;font-weight:bold;color:#1F3461;">{data['health']['points_with_data']}</div>
                            <div style="font-size:12px;color:#666;">Con Datos (24h)</div>
                        </td>
                        <td style="width:5%;"></td>
                        <td style="width:33%;text-align:center;background:#f8f9fa;padding:15px;border-radius:8px;">
                            <div style="font-size:28px;font-weight:bold;color:#1F3461;">{format_number(data['health']['total_measurements'])}</div>
                            <div style="font-size:12px;color:#666;">Mediciones (24h)</div>
                        </td>
                    </tr>
                </table>
    """
    
    # Puntos Desconectados
    if data['disconnected']:
        html += f"""
                <div class="section">
                    <div class="section-title">Puntos con dias de desconexion <span class="section-count">({len(data['disconnected'])} puntos)</span></div>
                    <table>
                        <tr>
                            <th>Codigo / Estandar</th>
                            <th>Punto / Cliente</th>
                            <th>Prov.</th>
                            <th>Ult. Medicion / Conexion</th>
                            <th>Dias</th>
                            <th>Total</th>
                            <th>Caudal</th>
                            <th>Nivel</th>
                        </tr>
        """
        for p in data['disconnected']:
            std_short = p['standard'][:3] if p['standard'] else ''
            tipo = ' (FORM)' if p.get('is_formulario') else ''
            
            # Valores conexión válida (únicos a mostrar)
            conn_total = format_number(p.get('conn_total', 0))
            conn_flow = round(p.get('conn_flow', 0), 2) if p.get('conn_flow') is not None else '-'
            conn_nivel = round(p.get('conn_nivel', 0), 2) if p.get('conn_nivel') is not None else '-'
            
            html += f"""
                        <tr>
                            <td><strong>{p['code_dga']}</strong><br><span class="badge-std">{std_short}</span>{tipo}</td>
                            <td><strong>{p['title'][:22]}</strong><br><span style="color:#888;font-size:10px;">{p['client'][:20]}</span></td>
                            <td>{p.get('proveedor', 'N/A')}</td>
                            <td>{p['last_date']}<br><span style="color:#52c41a;font-size:10px;">OK {p.get('last_connected_date', 'N/A')}</span></td>
                            <td><span class="badge-red">{p['days_disconnected']}d</span></td>
                            <td><span style="color:#52c41a;">{conn_total}</span></td>
                            <td><span style="color:#52c41a;">{conn_flow}</span></td>
                            <td><span style="color:#52c41a;">{conn_nivel}</span></td>
                        </tr>
            """
        html += "</table></div>"
    
    # Puntos Sin Variación (>24h)
    if data['stuck']:
        html += f"""
                <div class="section">
                    <div class="section-title">Puntos sin variacion (+24h) <span class="section-count">({len(data['stuck'])} puntos)</span></div>
                    <table>
                        <tr>
                            <th>Codigo / Estandar</th>
                            <th>Punto / Cliente</th>
                            <th>Prov.</th>
                            <th>Ult. Medicion / Variacion</th>
                            <th>Horas</th>
                            <th>Total</th>
                            <th>Caudal</th>
                            <th>Nivel</th>
                        </tr>
        """
        for p in data['stuck']:
            std_short = p['standard'][:3] if p['standard'] else ''
            
            # Valores actuales (arriba)
            last_total = format_number(p.get('last_total', 0))
            last_flow = round(p.get('last_flow', 0), 2) if p.get('last_flow') is not None else '-'
            last_nivel = round(p.get('last_nivel', 0), 2) if p.get('last_nivel') is not None else '-'
            
            # Valores variación válida (abajo, verde)
            var_total = format_number(p.get('var_total', 0))
            var_flow = round(p.get('var_flow', 0), 2) if p.get('var_flow') is not None else '-'
            var_nivel = round(p.get('var_nivel', 0), 2) if p.get('var_nivel') is not None else '-'
            
            html += f"""
                        <tr>
                            <td><strong>{p['code_dga']}</strong><br><span class="badge-std">{std_short}</span></td>
                            <td><strong>{p['title'][:22]}</strong><br><span style="color:#888;font-size:10px;">{p['client'][:20]}</span></td>
                            <td>{p.get('proveedor', 'N/A')}</td>
                            <td>{p.get('last_date', 'N/A')}<br><span style="color:#52c41a;font-size:10px;">OK {p.get('last_variation_date', 'N/A')}</span></td>
                            <td><span class="badge-yellow">+{p['hours_stuck']}h</span></td>
                            <td>{last_total}<br><span style="color:#52c41a;font-size:10px;">{var_total}</span></td>
                            <td>{last_flow}<br><span style="color:#52c41a;font-size:10px;">{var_flow}</span></td>
                            <td>{last_nivel}<br><span style="color:#52c41a;font-size:10px;">{var_nivel}</span></td>
                        </tr>
            """
        html += "</table></div>"
    
    # Resets con detalle de últimos 5 eventos
    if data['resets']:
        total_eventos = sum(r['count'] for r in data['resets'])
        html += f"""
                <div class="section">
                    <div class="section-title">Reinicios de Contador (24h) <span class="section-count">({len(data['resets'])} puntos, {total_eventos} eventos)</span></div>
        """
        for p in data['resets']:
            badge_class = "badge-critical" if p['is_critical'] else "badge-yellow"
            estado = "CRITICO" if p['is_critical'] else ""
            html += f"""
                    <div style="background:#fff8e6;padding:10px;border-radius:6px;margin-bottom:10px;border-left:4px solid #faad14;">
                        <strong>{p['title']}</strong> {estado} 
                        <span class="{badge_class}">{p['count']} reinicios</span>
                        <span style="color:#888;font-size:11px;">| Codigo: {p['code_dga'] or 'N/A'} | Cliente: {p['client']}</span>
                        <table style="margin-top:8px;">
                            <tr><th>Fecha</th><th>Valor Anterior</th><th>Valor Nuevo</th></tr>
            """
            for ev in p.get('events', []):
                html += f"""
                            <tr>
                                <td>{ev['date']}</td>
                                <td>{format_number(ev['val_anterior'])}</td>
                                <td>{format_number(ev['val_actual'])}</td>
                            </tr>
                """
            html += """
                        </table>
                    </div>
            """
        html += "</div>"
    
    # Puntos con Constante
    if data['with_addition']:
        html += f"""
                <div class="section">
                    <div class="section-title">Puntos con Constante por Reinicio <span class="section-count">({len(data['with_addition'])} puntos)</span></div>
                    <table>
                        <tr><th>Codigo Obra</th><th>Estandar</th><th>Punto</th><th>Cliente</th><th>Constante</th><th>Total Actual</th></tr>
        """
        for p in data['with_addition']:
            std_short = p['standard'][:3] if p['standard'] else ''
            html += f"""
                        <tr>
                            <td>{p['code_dga']}</td>
                            <td><span class="badge-std">{std_short}</span></td>
                            <td>{p['title'][:25]}</td>
                            <td>{p['client'][:18]}</td>
                            <td><span class="badge-blue">{format_number(p['addition'])}</span></td>
                            <td>{format_number(p['last_total'])}</td>
                        </tr>
            """
        html += "</table></div>"
    
    # Formularios sin datos
    if data.get('formularios_sin_datos'):
        html += f"""
                <div class="section">
                    <div class="section-title">Formularios Sin Datos <span class="section-count">({len(data['formularios_sin_datos'])} puntos)</span></div>
                    <table>
                        <tr><th>Código Obra</th><th>Punto</th><th>Cliente</th></tr>
        """
        for p in data['formularios_sin_datos']:
            html += f"""
                        <tr>
                            <td>{p['code_dga']}</td>
                            <td>{p['title'][:30]}</td>
                            <td>{p['client'][:25]}</td>
                        </tr>
            """
        html += "</table></div>"
    
    html += """
            </div>
            
            <div class="footer">
                Sistema de Telemetría SmartHydro - Reporte automático generado por el sistema
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def generate_text_bulletin(data):
    """Generar versión texto plano del boletín"""
    now = timezone.now()
    text = f"Boletin Diario de Telemetria - {now.strftime('%d/%m/%Y')}\n"
    text += "=" * 40 + "\n\n"
    
    text += f"SALUD DEL SISTEMA: {data['health']['health_pct']}%\n"
    text += f"Puntos Activos: {data['health']['total_active']}\n"
    text += f"Con Datos Hoy: {data['health']['points_with_data']}\n"
    text += f"Mediciones: {data['health']['total_measurements']}\n\n"
    
    if data['disconnected']:
        text += f"--- PUNTOS DESCONECTADOS ({len(data['disconnected'])}) ---\n"
        for p in data['disconnected']:
            text += f"* {p['title']} ({p['client']}) - {p['days_disconnected']} dias\n"
            text += f"  Ult. vez: {p['last_date']}\n"
        text += "\n"
        
    if data['stuck']:
        text += f"--- PUNTOS SIN VARIACION ({len(data['stuck'])}) ---\n"
        for p in data['stuck']:
            text += f"* {p['title']} ({p['client']}) - {p['hours_stuck']}h sin cambio\n"
        text += "\n"
        
    if data['resets']:
        text += f"--- REINICIOS ({len(data['resets'])}) ---\n"
        for p in data['resets']:
            text += f"* {p['title']} - {p['count']} reinicios\n"
            
    text += "\nSistema SmartHydro\n"
    return text


def run():
    """Ejecutar el cronjob del boletín diario"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    
    logger.info("📧 Iniciando generación de boletín diario...")
    
    try:
        # Obtener datos crudos
        disconnected = get_disconnected_points()
        stuck_raw = get_stuck_points()
        
        # FILTRO: Si un punto está desconectado, NO debe aparecer en sin variación
        disconnected_ids = {d['id'] for d in disconnected}
        stuck = [s for s in stuck_raw if s['id'] not in disconnected_ids]
        
        data = {
            'health': get_health_summary(exclude_ids=disconnected_ids),
            'disconnected': disconnected,
            'stuck': stuck,
            'resets': get_recent_resets_summary(),
            'with_addition': get_points_with_addition(),
            'formularios_sin_datos': get_formularios_sin_datos()
        }
        
        html_content = generate_html_bulletin(data)
        text_content = generate_text_bulletin(data)
        
        recipients = get_staff_emails() + ADDITIONAL_RECIPIENTS
        recipients = list(set(recipients))
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados")
            return
        
        host = settings.EMAIL_HOST
        port = settings.EMAIL_PORT
        use_ssl = settings.EMAIL_USE_SSL
        user = settings.EMAIL_HOST_USER
        password = settings.EMAIL_HOST_PASSWORD

        now = timezone.now()
        subject = f"📊 Boletín Telemetría SmartHydro - {now.strftime('%d/%m/%Y')} - Salud: {data['health']['health_pct']}%"

        # Usar SMTP_SSL para puerto 465, SMTP + starttls para puerto 587
        if use_ssl and port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
            server.login(user, password)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
            server.login(user, password)

        # Nombre amigable del remitente
        from_header = f"SmartHydro Telemetría <{user}>"

        for recipient in recipients:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_header
            msg['To'] = recipient
            msg['Reply-To'] = user

            # Headers adicionales para evitar spam
            msg['X-Mailer'] = 'SmartHydro Telemetry System'
            msg['X-Priority'] = '3'

            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))

            server.sendmail(user, recipient, msg.as_string())
        
        server.quit()
        
        logger.info(f"✅ Boletín enviado a {len(recipients)} destinatarios")
        print(f"✅ Boletín enviado a: {', '.join(recipients)}")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        print(f"❌ Error: {e}")
        raise
