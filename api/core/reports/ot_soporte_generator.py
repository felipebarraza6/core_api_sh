"""
Generador de PDF para Órdenes de Trabajo de Soporte (OT Soporte-HW)
===================================================================

Genera PDFs con información completa del punto para revisión de soporte:
- Información del punto y configuración
- Historial de anomalías detectadas
- Últimos valores correctos
- Sugerencias de intervención
"""

from io import BytesIO
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from django.db.models import Max, Min, Avg, Count, Sum, F
from django.db.models.functions import TruncMonth, TruncDay
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
import pytz
import urllib.request

from api.core.models import (
    CatchmentPoint, InteractionDetail, Variable, 
    ProfileDataConfigCatchment, DgaDataConfigCatchment,
    NotificationsCatchment
)


# Colores SmartHydro
WATER_BLUE = colors.HexColor('#0066CC')
WATER_LIGHT = colors.HexColor('#E6F2FF')
WATER_DARK = colors.HexColor('#003366')
WARNING_ORANGE = colors.HexColor('#FF6600')
ERROR_RED = colors.HexColor('#CC0000')
SUCCESS_GREEN = colors.HexColor('#00AA00')


def detect_provider_from_token(token_service: str) -> str:
    """Detectar proveedor basado en el token de servicio."""
    if not token_service:
        return "Sin configurar"
    token_lower = token_service.lower()
    if 'nettra' in token_lower or len(token_service) == 40:
        return "Nettra"
    elif 'tago' in token_lower:
        return "TagoIO"
    elif 'novus' in token_lower:
        return "Novus"
    else:
        return "Otro"


def calculate_days_without_data(point_id: int) -> Tuple[int, Optional[datetime]]:
    """Calcular días sin datos nuevos y fecha del último registro."""
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    
    last_record = InteractionDetail.objects.filter(
        catchment_point_id=point_id
    ).order_by('-date_time_medition').first()
    
    if not last_record or not last_record.date_time_medition:
        return -1, None
    
    last_date = last_record.date_time_medition
    if last_date.tzinfo is None:
        last_date = chile_tz.localize(last_date)
    
    days_diff = (now - last_date).days
    return days_diff, last_date


def get_last_correct_values(point_id: int) -> Dict:
    """Obtener últimos valores correctos por cada variable."""
    chile_tz = pytz.timezone("America/Santiago")
    
    # Obtener último registro con datos válidos
    last_valid = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        total__isnull=False
    ).exclude(total='').order_by('-date_time_medition').first()
    
    if not last_valid:
        return {}
    
    # Obtener variables del punto
    variables = Variable.objects.filter(
        scheme_catchment__points_catchment__id=point_id
    )
    
    result = {
        'fecha': last_valid.date_time_medition.strftime('%Y-%m-%d %H:%M') if last_valid.date_time_medition else 'N/A',
        'valores': {}
    }
    
    for var in variables:
        if var.type_variable == 'TOTALIZADO' and last_valid.total:
            pf = var.pulses_factor if var.pulses_factor else 1000
            result['valores'][f'VolumenAcum (factor {pf})'] = int(float(last_valid.total))
        elif var.type_variable == 'NIVEL' and last_valid.nivel:
            result['valores']['Nivel (base 1)'] = float(last_valid.nivel)
        elif var.type_variable in ['CAUDAL', 'CAUDAL_PROMEDIO'] and last_valid.flow:
            result['valores']['Caudal (L/s)'] = float(last_valid.flow)
    
    return result


def detect_anomalies_optimized(point_id: int, months_back: int = 6) -> List[Dict]:
    """
    Detectar anomalías en el historial con estrategias de rendimiento.
    
    Estrategias:
    1. Procesar por mes para no cargar todo en memoria
    2. Usar agregaciones de BD cuando sea posible
    3. Limitar detalle a últimos N meses
    """
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    start_date = now - timedelta(days=months_back * 30)
    
    anomalies = []
    
    # 1. Resets detectados (de NotificationsCatchment)
    reset_notifications = NotificationsCatchment.objects.filter(
        point_catchment_id=point_id,
        title__icontains='Reinicio'
    ).order_by('-start_date')[:10]
    
    for notif in reset_notifications:
        # Buscar registro cercano para obtener pulsos/total
        nearby_rec = InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__lte=notif.start_date
        ).order_by('-date_time_medition').first()
        
        vals_str = ""
        if nearby_rec:
            p = int(nearby_rec.pulses) if nearby_rec.pulses is not None else 'N/A'
            t = int(float(nearby_rec.total)) if nearby_rec.total else 'N/A'
            vals_str = f" [Pulsos: {p}, Total: {t}]"

        anomalies.append({
            'tipo': 'RESET',
            'severidad': 'ADVERTENCIA',
            'fecha': notif.start_date.strftime('%Y-%m-%d') if notif.start_date else 'N/A',
            'descripcion': (notif.message[:80] if notif.message else 'Reset detectado') + vals_str
        })
    
    # 2. Gaps de datos (días sin registros) usando agregación
    daily_counts = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=start_date
    ).annotate(
        dia=TruncDay('date_time_medition')
    ).values('dia').annotate(
        count=Count('id')
    ).order_by('dia')
    
    daily_counts_list = list(daily_counts)
    prev_day = None
    for dc in daily_counts_list:
        if prev_day and dc['dia']:
            gap = (dc['dia'] - prev_day).days
            if gap > 1:
                # Buscar último registro antes del gap
                last_rec = InteractionDetail.objects.filter(
                    catchment_point_id=point_id,
                    date_time_medition__lt=dc['dia']
                ).order_by('-date_time_medition').first()
                
                vals_str = ""
                if last_rec:
                    p = int(last_rec.pulses) if last_rec.pulses is not None else 'N/A'
                    t = int(float(last_rec.total)) if last_rec.total else 'N/A'
                    vals_str = f" [Último: P={p}, T={t}]"

                anomalies.append({
                    'tipo': 'GAP_DATOS',
                    'severidad': 'CRÍTICA' if gap > 3 else 'ADVERTENCIA',
                    'fecha': prev_day.strftime('%Y-%m-%d'),
                    'descripcion': f'Sin datos por {gap} días{vals_str}'
                })
        prev_day = dc['dia']
    
    # 3. Valores extremos usando agregaciones
    point = CatchmentPoint.objects.filter(id=point_id).first()
    profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_id).first()
    
    if profile:
        # Caudal imposible
        if profile.d5:
            from api.core.validators.telemetry_validator import calculate_max_flow_by_diameter
            max_flow = calculate_max_flow_by_diameter(float(profile.d5))
            
            impossible_flows = InteractionDetail.objects.filter(
                catchment_point_id=point_id,
                date_time_medition__gte=start_date,
                flow__gt=max_flow
            ).count()
            
            if impossible_flows > 0:
                # Obtener un ejemplo
                bad_rec = InteractionDetail.objects.filter(
                    catchment_point_id=point_id,
                    date_time_medition__gte=start_date,
                    flow__gt=max_flow
                ).first()
                vals_str = ""
                if bad_rec:
                    vals_str = f" [Ej: {float(bad_rec.flow):.2f} L/s]"

                anomalies.append({
                    'tipo': 'CAUDAL_IMPOSIBLE',
                    'severidad': 'CRÍTICA',
                    'fecha': f'Últimos {months_back} meses',
                    'descripcion': f'{impossible_flows} registros > {max_flow:.2f} L/s{vals_str}'
                })
        
        # Nivel imposible
        if profile.d1:
            impossible_levels = InteractionDetail.objects.filter(
                catchment_point_id=point_id,
                date_time_medition__gte=start_date,
                nivel__gt=float(profile.d1)
            ).count()
            
            if impossible_levels > 0:
                bad_rec = InteractionDetail.objects.filter(
                    catchment_point_id=point_id,
                    date_time_medition__gte=start_date,
                    nivel__gt=float(profile.d1)
                ).first()
                vals_str = ""
                if bad_rec:
                    vals_str = f" [Ej: {float(bad_rec.nivel):.2f} m]"

                anomalies.append({
                    'tipo': 'NIVEL_IMPOSIBLE',
                    'severidad': 'CRÍTICA',
                    'fecha': f'Últimos {months_back} meses',
                    'descripcion': f'{impossible_levels} registros > {profile.d1}m{vals_str}'
                })
    
    # 4. Datos estancados (mismo valor por > 24h)
    # Usar muestreo para rendimiento
    sample_records = list(InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=start_date,
        total__isnull=False
    ).order_by('date_time_medition').values('date_time_medition', 'total')[:5000:10])  # cada 10vo registro
    
    if len(sample_records) > 2:
        prev_total = None
        stagnant_start = None
        for rec in sample_records:
            if prev_total is not None and rec['total'] == prev_total:
                if stagnant_start is None:
                    stagnant_start = rec['date_time_medition']
            else:
                if stagnant_start and rec['date_time_medition']:
                    hours_stagnant = (rec['date_time_medition'] - stagnant_start).total_seconds() / 3600
                    if hours_stagnant > 24:
                        # Buscar pulsos en ese momento
                        st_rec = InteractionDetail.objects.filter(
                            catchment_point_id=point_id,
                            date_time_medition=stagnant_start
                        ).first()
                        p = int(st_rec.pulses) if st_rec and st_rec.pulses is not None else 'N/A'
                        
                        anomalies.append({
                            'tipo': 'DATOS_ESTANCADOS',
                            'severidad': 'ADVERTENCIA',
                            'fecha': stagnant_start.strftime('%Y-%m-%d'),
                            'descripcion': f'Total {prev_total} fijo por {int(hours_stagnant)}h [Pulsos: {p}]'
                        })
                stagnant_start = None
            prev_total = rec['total']
    
    # Ordenar por severidad
    severity_order = {'CRÍTICA': 0, 'ADVERTENCIA': 1, 'INFO': 2}
    anomalies.sort(key=lambda x: (severity_order.get(x['severidad'], 3), x['fecha']), reverse=True)
    
    return anomalies[:20]  # Limitar a 20 anomalías


def suggest_intervention_type(anomalies: List[Dict], days_without_data: int) -> str:
    """Sugerir tipo de intervención basado en anomalías detectadas."""
    if days_without_data > 7:
        return "Revisión de logger en terreno"
    
    critical_count = sum(1 for a in anomalies if a['severidad'] == 'CRÍTICA')
    
    if critical_count > 5:
        return "Revisión completa de hardware y sensores"
    elif critical_count > 0:
        return "Revisión de sensores"
    elif any(a['tipo'] == 'GAP_DATOS' for a in anomalies):
        return "Verificación de conectividad"
    elif any(a['tipo'] == 'DATOS_ESTANCADOS' for a in anomalies):
        return "Verificación de sensor totalizador"
    else:
        return "Mantenimiento preventivo"


def get_urgency_level(days_without_data: int, critical_anomalies: int) -> Tuple[str, str]:
    """Determinar nivel de urgencia y color."""
    if days_without_data > 30 or critical_anomalies > 10:
        return "ALTA", "#CC0000"
    elif days_without_data > 7 or critical_anomalies > 3:
        return "MEDIA", "#FF6600"
    else:
        return "BAJA", "#00AA00"


def generate_ot_soporte_pdf(point_id: int, motivo: str = None, contacto_cliente: str = None) -> BytesIO:
    """
    Generar PDF de Orden de Trabajo para Soporte-HW.
    
    Args:
        point_id: ID del punto de captación
        motivo: Motivo del requerimiento (opcional)
        contacto_cliente: Email/teléfono del contacto (opcional)
    
    Returns:
        BytesIO con el PDF generado
    """
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    
    # Obtener datos del punto
    try:
        point = CatchmentPoint.objects.select_related('project__client').get(id=point_id)
    except CatchmentPoint.DoesNotExist:
        raise ValueError(f"Punto {point_id} no encontrado")
    
    profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_id).first()
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=point_id).first()
    variables = Variable.objects.filter(scheme_catchment__points_catchment__id=point_id)
    
    # Calcular métricas
    days_without_data, last_data_date = calculate_days_without_data(point_id)
    last_values = get_last_correct_values(point_id)
    anomalies = detect_anomalies_optimized(point_id, months_back=6)
    critical_count = sum(1 for a in anomalies if a['severidad'] == 'CRÍTICA')
    intervention_type = suggest_intervention_type(anomalies, days_without_data)
    urgency, urgency_color = get_urgency_level(days_without_data, critical_count)
    
    # Generar número OT
    ot_number = f"{now.year}_S_{point_id:03d}"
    
    # Crear PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50,
                           topMargin=60, bottomMargin=50)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16,
                                  textColor=WATER_DARK, alignment=1, spaceAfter=20)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=12,
                                    textColor=WATER_BLUE, spaceBefore=15, spaceAfter=8)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10,
                                   spaceAfter=6)
    
    # Logo
    try:
        logo_url = "https://smarthydro.cl/wp-content/uploads/2023/12/SmartHydro-Logo.png"
        logo_path = "/tmp/smarthydro_logo_ot.png"
        urllib.request.urlretrieve(logo_url, logo_path)
        from reportlab.platypus import Image
        logo = Image(logo_path, width=2*inch, height=0.8*inch)
        elements.append(logo)
        elements.append(Spacer(1, 0.1*inch))
    except:
        pass
    
    # Título
    elements.append(Paragraph("Orden de Trabajo Servicio (OT)", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # ========== 1. ENCABEZADO ==========
    elements.append(Paragraph("<b>1. Encabezado</b>", section_style))
    
    # Detectar proveedor
    provider = detect_provider_from_token(profile.token_service if profile else None)
    
    # Variables del punto
    vars_list = ", ".join([v.type_variable.lower().replace('_', ' ') for v in variables]) or "Sin variables"
    
    header_data = [
        ['Número de OT:', ot_number],
        ['Fecha de emisión:', now.strftime('%d-%m-%Y')],
        ['Nombre del cliente:', point.project.client.name if point.project and point.project.client else 'N/A'],
        ['Nombre de punto:', point.title],
        ['Proveedor:', provider],
        ['IMEI/Token:', profile.token_service[:50] + '...' if profile and profile.token_service and len(profile.token_service) > 50 else (profile.token_service if profile else 'N/A')],
        ['Ubicación:', f"{point.lat}, {point.lon}" if point.lat and point.lon else 'Pendiente'],
        ['Variables:', vars_list],
    ]
    
    header_table = Table(header_data, colWidths=[2*inch, 4*inch])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), WATER_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # ========== 2. DESCRIPCIÓN DEL PROBLEMA ==========
    elements.append(Paragraph("<b>2. Descripción del problema o solicitud</b>", section_style))
    elements.append(Paragraph("<b>○ Motivo del requerimiento:</b>", normal_style))
    
    if motivo:
        elements.append(Paragraph(f"    1. {motivo}", normal_style))
    elif days_without_data > 0:
        elements.append(Paragraph(f"    1. Punto en uso, pero sin conexión desde hace {days_without_data} días.", normal_style))
    else:
        elements.append(Paragraph("    1. Revisión preventiva solicitada.", normal_style))
    
    elements.append(Spacer(1, 0.15*inch))
    
    # ========== 3. REVISIÓN PREVIA ==========
    elements.append(Paragraph("<b>3. Revisión previa</b>", section_style))
    
    if days_without_data >= 0:
        elements.append(Paragraph(f"○ El punto se encuentra sin datos nuevos desde hace <b>{days_without_data} días</b>", normal_style))
    else:
        elements.append(Paragraph("○ El punto no tiene registros históricos", normal_style))
    
    if last_values and last_values.get('valores'):
        elements.append(Paragraph(f"○ <b>Últimos valores correctos</b> ({last_values.get('fecha', 'N/A')}):", normal_style))
        
        values_data = [[k, str(v)] for k, v in last_values['valores'].items()]
        if values_data:
            values_table = Table(values_data, colWidths=[2.5*inch, 2*inch])
            values_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), WATER_LIGHT),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(values_table)
    
    elements.append(Spacer(1, 0.15*inch))
    
    # ========== ESTADÍSTICAS DE PULSOS Y TOTALIZADO ==========
    elements.append(Paragraph("<b>○ Estado de Pulsos y Totalizado (últimos 6 meses):</b>", normal_style))
    elements.append(Spacer(1, 0.05*inch))
    
    # Obtener estadísticas de pulsos
    chile_tz = pytz.timezone("America/Santiago")
    six_months_ago = datetime.now(chile_tz) - timedelta(days=180)
    
    pulse_stats = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=six_months_ago,
        pulses__isnull=False
    ).aggregate(
        total_records=Count('id'),
        min_pulses=Min('pulses'),
        max_pulses=Max('pulses'),
        avg_pulses=Avg('pulses')
    )
    
    total_stats = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=six_months_ago,
        total__isnull=False
    ).exclude(total='').aggregate(
        min_total=Min('total'),
        max_total=Max('total')
    )
    
    # Calcular consumo total del período
    consumo_periodo = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=six_months_ago,
        total_diff__isnull=False
    ).aggregate(sum_diff=Sum('total_diff'))['sum_diff'] or 0
    
    # Formatear números
    def fmt(val):
        if val is None:
            return 'N/A'
        try:
            return f"{int(float(val)):,}".replace(',', '.')
        except:
            return str(val)
    
    stats_data = [
        ['Métrica', 'Pulsos', 'Total (m³)'],
        ['Registros analizados', fmt(pulse_stats['total_records']), '-'],
        ['Valor mínimo', fmt(pulse_stats['min_pulses']), fmt(total_stats['min_total'])],
        ['Valor máximo', fmt(pulse_stats['max_pulses']), fmt(total_stats['max_total'])],
        ['Promedio', fmt(pulse_stats['avg_pulses']), '-'],
        ['Consumo del período', '-', f"{fmt(consumo_periodo)} m³"],
    ]
    
    stats_table = Table(stats_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), WATER_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 1), (0, -1), WATER_LIGHT),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (1, 1), (-1, -1), [colors.white, WATER_LIGHT]),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 0.15*inch))
    
    # ========== ANOMALÍAS DETECTADAS ==========
    if anomalies:
        elements.append(Paragraph("<b>○ Anomalías detectadas en historial (últimos 6 meses):</b>", normal_style))
        elements.append(Spacer(1, 0.05*inch))
        
        # Crear filas con datos mejorados
        anomaly_data = [['', 'Tipo', 'Severidad', 'Fecha', 'Descripción']]
        row_colors = []  # Para aplicar colores por fila
        
        for idx, a in enumerate(anomalies[:10]):  # Máximo 10
            # Iconos según tipo
            icon = '🔄' if a['tipo'] == 'RESET' else ('📉' if 'GAP' in a['tipo'] else ('⚠️' if 'ESTANCADO' in a['tipo'] else '❌'))
            
            # Formatear tipo más legible
            tipo_display = a['tipo'].replace('_', ' ').title()
            
            # Descripción completa (Paragraph se ajustará automáticamente)
            desc = a['descripcion']
            
            anomaly_data.append([icon, tipo_display, a['severidad'], a['fecha'], desc])
            
            # Guardar color según severidad
            if a['severidad'] == 'CRÍTICA':
                row_colors.append(colors.HexColor('#FFE6E6'))  # Rojo claro
            else:
                row_colors.append(colors.HexColor('#FFF9E6'))  # Amarillo claro
        
        # Aumentamos ancho de descripción para evitar cortes (Total ~6.7 inch)
        anomaly_table = Table(anomaly_data, colWidths=[0.3*inch, 1.1*inch, 0.9*inch, 0.9*inch, 3.5*inch])
        
        # Estilo base
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), WATER_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Iconos centrados
            ('ALIGN', (2, 0), (3, -1), 'CENTER'),  # Severidad y Fecha centrados
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]
        
        # Aplicar colores por fila según severidad
        for idx, row_color in enumerate(row_colors):
            table_style.append(('BACKGROUND', (0, idx+1), (-1, idx+1), row_color))
            # Texto rojo para CRÍTICA
            if anomalies[idx]['severidad'] == 'CRÍTICA':
                table_style.append(('TEXTCOLOR', (2, idx+1), (2, idx+1), ERROR_RED))
                table_style.append(('FONTNAME', (2, idx+1), (2, idx+1), 'Helvetica-Bold'))
        
        anomaly_table.setStyle(TableStyle(table_style))
        elements.append(anomaly_table)
        
        # Leyenda
        elements.append(Spacer(1, 0.05*inch))
        elements.append(Paragraph(
            "<i><font size='7' color='#666666'>🔄 Reset de contador | 📉 Gap de datos | ⚠️ Datos estancados | ❌ Valor imposible</font></i>",
            normal_style
        ))
    
    elements.append(Spacer(1, 0.15*inch))
    
    # ========== 4. ESPECIFICACIONES DEL TRABAJO ==========
    elements.append(Paragraph("<b>4. Especificaciones del trabajo solicitado</b>", section_style))
    elements.append(Paragraph("<b>○ Tipo de intervención requerida:</b>", normal_style))
    elements.append(Paragraph(f"    1. {intervention_type}", normal_style))
    elements.append(Spacer(1, 0.15*inch))
    
    # ========== 5. PRIORIDAD Y PLAZO ==========
    elements.append(Paragraph("<b>5. Prioridad y plazo</b>", section_style))
    
    urgency_msg = f"Punto sin datos hace {days_without_data} días" if days_without_data > 0 else "Revisión preventiva"
    if critical_count > 0:
        urgency_msg += f", {critical_count} anomalías críticas detectadas"
    
    elements.append(Paragraph(f"○ <b>Nivel de urgencia:</b> {urgency} - {urgency_msg}", normal_style))
    elements.append(Paragraph("○ <b>Plazo requerido:</b> Definido por Hardware.", normal_style))
    elements.append(Spacer(1, 0.15*inch))
    
    # ========== 6. DATOS DE CONTACTO ==========
    elements.append(Paragraph("<b>6. Datos de contacto</b>", section_style))
    
    client_email = contacto_cliente or (point.project.client.contact_email if point.project and point.project.client and hasattr(point.project.client, 'contact_email') else 'Sin detalle')
    elements.append(Paragraph(f"○ <b>Persona de contacto del cliente:</b> {client_email}", normal_style))
    elements.append(Paragraph("○ <b>Contacto interno (soporte):</b> Sin detalle.", normal_style))
    elements.append(Spacer(1, 0.15*inch))
    
    # ========== 7. APROBACIONES ==========
    elements.append(Paragraph("<b>7. Aprobaciones</b>", section_style))
    elements.append(Paragraph("○ <b>Autorización interna:</b> Pendiente.", normal_style))
    elements.append(Paragraph("○ <b>Aprobación del cliente (si aplica):</b> Pendiente.", normal_style))
    
    # Construir PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
