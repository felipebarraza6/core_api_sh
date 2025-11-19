"""
Generador de PDFs para análisis de telemetría
=============================================

Genera PDFs con análisis de coherencia de datos de telemetría.
Este reporte es generado automáticamente por API Smart Hydro.
"""

from io import BytesIO
from datetime import datetime
from typing import List, Dict, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, Line, Circle, String
from reportlab.graphics import renderPDF
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.widgets.markers import makeMarker
import math
import urllib.request
from api.core.validators.telemetry_validator import analyze_data_coherence


def format_number_with_thousands(value):
    """Formatear número con puntos de miles."""
    if value is None:
        return 'Sin registros'
    try:
        return f"{int(value):,}".replace(',', '.')
    except (ValueError, TypeError):
        return str(value)


def format_decimal(value, decimals=2):
    """Formatear decimal con puntos de miles."""
    if value is None:
        return 'Sin registros'
    try:
        return f"{float(value):,.{decimals}f}".replace(',', '.')
    except (ValueError, TypeError):
        return str(value)


def calculate_variation_percentage(min_val, max_val):
    """Calcular variación como porcentaje."""
    if min_val is None or max_val is None or min_val == 0:
        return None
    try:
        return ((max_val - min_val) / min_val) * 100
    except (ZeroDivisionError, TypeError):
        return None


def get_variation_color(variation_percent):
    """Obtener color según variación: verde < 30%, amarillo >= 30%."""
    if variation_percent is None:
        return colors.HexColor('#CCCCCC')  # Gris para N/A
    if variation_percent < 30:
        return colors.HexColor('#00CC00')  # Verde
    else:
        return colors.HexColor('#FFCC00')  # Amarillo


def create_line_chart(data_points, title, y_label, color, width=500, height=250, max_points=100):
    """
    Crear gráfico de línea mejorado y explicativo para ReportLab.
    
    Args:
        data_points: Lista de valores numéricos
        title: Título del gráfico
        y_label: Etiqueta del eje Y
        color: Color de la línea (hex)
        width: Ancho del gráfico
        height: Alto del gráfico
        max_points: Máximo de puntos a mostrar (si hay más, se muestrean)
    
    Returns:
        Drawing con el gráfico mejorado
    """
    from reportlab.graphics.shapes import Drawing, String, Rect, Line, Circle
    from reportlab.graphics.charts.lineplots import LinePlot
    
    drawing = Drawing(width, height)
    
    # Si hay demasiados puntos, muestrear
    if len(data_points) > max_points:
        step = len(data_points) // max_points
        data_points = data_points[::step]
    
    if not data_points or len(data_points) < 2:
        # Gráfico vacío con mensaje explicativo
        drawing.add(String(width/2, height/2, 'Sin datos suficientes para generar gráfico', 
                          textAnchor='middle', fontSize=10, fillColor=colors.grey))
        return drawing
    
    # Crear gráfico de línea mejorado
    lp = LinePlot()
    lp.x = 70
    lp.y = 50
    lp.width = width - 140
    lp.height = height - 100
    
    # Preparar datos (normalizar índices)
    data = [(i, val) for i, val in enumerate(data_points)]
    lp.data = [data]
    
    # Configurar colores y estilo mejorado
    lp.lines[0].strokeColor = colors.HexColor(color)
    lp.lines[0].strokeWidth = 2.5
    
    # Configurar ejes con mejor formato
    lp.xValueAxis.valueMin = 0
    lp.xValueAxis.valueMax = len(data_points) - 1
    lp.xValueAxis.labelTextFormat = '%d'
    lp.xValueAxis.labels.fontSize = 8
    lp.xValueAxis.labels.fillColor = colors.HexColor('#333333')
    
    min_val = min(data_points)
    max_val = max(data_points)
    margin = (max_val - min_val) * 0.15 if max_val != min_val else 1
    lp.yValueAxis.valueMin = max(0, min_val - margin)
    lp.yValueAxis.valueMax = max_val + margin
    lp.yValueAxis.labelTextFormat = '%.1f'
    lp.yValueAxis.labels.fontSize = 8
    lp.yValueAxis.labels.fillColor = colors.HexColor('#333333')
    
    # Fondo del gráfico con cuadrícula sutil
    bg_rect = Rect(lp.x - 5, lp.y - 5, lp.width + 10, lp.height + 10,
                   fillColor=colors.HexColor('#FAFAFA'),
                   strokeColor=colors.HexColor('#E0E0E0'),
                   strokeWidth=1)
    drawing.add(bg_rect)
    
    # Título mejorado con fondo
    title_bg = Rect(width/2 - 120, height - 35, 240, 25,
                   fillColor=colors.HexColor('#E6F2FF'),
                   strokeColor=colors.HexColor('#0066CC'),
                   strokeWidth=1)
    drawing.add(title_bg)
    drawing.add(String(width/2, height - 22, title, 
                      textAnchor='middle', fontSize=12, fillColor=colors.HexColor('#003366'),
                      fontName='Helvetica-Bold'))
    
    # Etiqueta eje Y mejorada
    drawing.add(String(25, height/2, y_label, 
                      textAnchor='middle', fontSize=10, fillColor=colors.HexColor('#0066CC'),
                      angle=90, fontName='Helvetica-Bold'))
    
    # Etiqueta eje X
    drawing.add(String(width/2, 25, 'Mediciones (orden cronológico)', 
                      textAnchor='middle', fontSize=9, fillColor=colors.HexColor('#666666')))
    
    # Estadísticas en una caja informativa
    stats_text = f"Min: {min_val:.2f} | Max: {max_val:.2f} | Prom: {sum(data_points)/len(data_points):.2f}"
    stats_bg = Rect(width - 200, height - 30, 190, 20,
                   fillColor=colors.HexColor('#FFF9E6'),
                   strokeColor=colors.HexColor('#FFCC00'),
                   strokeWidth=1)
    drawing.add(stats_bg)
    drawing.add(String(width - 105, height - 20, stats_text,
                      textAnchor='middle', fontSize=7, fillColor=colors.HexColor('#666666')))
    
    # Icono informativo (círculo con "i")
    info_circle = Circle(width - 15, height - 15, 8,
                        fillColor=colors.HexColor('#0066CC'),
                        strokeColor=colors.white,
                        strokeWidth=1)
    drawing.add(info_circle)
    drawing.add(String(width - 15, height - 18, 'i',
                      textAnchor='middle', fontSize=10, fillColor=colors.white,
                      fontName='Helvetica-Bold'))
    
    drawing.add(lp)
    return drawing


def generate_telemetry_analysis_pdf(points: List, project_name: Optional[str] = None, user_info: Optional[str] = None) -> BytesIO:
    """
    Generar PDF de análisis de telemetría para uno o más puntos.
    
    Args:
        points: Lista de IDs de puntos de captación o instancias CatchmentPoint
        project_name: Nombre del proyecto (si es por proyecto)
        user_info: Información del usuario que genera el informe (opcional)
    
    Returns:
        BytesIO con el PDF generado
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50,
                           topMargin=60, bottomMargin=50)
    
    # Contenedor para elementos del PDF
    elements = []
    
    # Estilos con colores de agua
    styles = getSampleStyleSheet()
    
    # Colores de agua (azules)
    water_blue = colors.HexColor('#0066CC')
    water_light_blue = colors.HexColor('#E6F2FF')
    water_medium_blue = colors.HexColor('#4A90E2')
    water_light_blue_alt = colors.HexColor('#B3D9FF')
    water_dark_blue = colors.HexColor('#003366')
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=water_dark_blue,
        spaceAfter=30,
        alignment=1  # Centrado
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=water_blue,
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Estilo para textos naturales (mejorado con párrafos más grandes)
    natural_text_style = ParagraphStyle(
        'NaturalText',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#333333'),
        spaceAfter=10,
        spaceBefore=5,
        leading=14
    )
    
    # Logo SmartHydro
    try:
        logo_url = "https://smarthydro.cl/wp-content/uploads/2023/12/SmartHydro-Logo.png"
        logo_path = "/tmp/smarthydro_logo.png"
        urllib.request.urlretrieve(logo_url, logo_path)
        logo = Image(logo_path, width=2*inch, height=0.8*inch)
        elements.append(logo)
        elements.append(Spacer(1, 0.1*inch))
    except Exception as e:
        # Si no se puede cargar el logo, continuar sin él
        pass
    
    # Título
    if project_name:
        title = f"Análisis de Telemetría - Proyecto: {project_name}"
    else:
        title = f"Análisis de Telemetría - {len(points)} Punto(s)"
    
    elements.append(Paragraph(title, title_style))
    fecha_gen = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elements.append(Paragraph(f"Fecha de generación: {fecha_gen}", natural_text_style))
    if user_info:
        elements.append(Paragraph(f"Generado por: {user_info}", natural_text_style))
    elements.append(Paragraph("Este reporte ha sido generado automáticamente por API Smart Hydro para el análisis de datos de telemetría.", natural_text_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Analizar cada punto
    from api.core.models import CatchmentPoint
    
    for point_data in points:
        if isinstance(point_data, int):
            point_id = point_data
            try:
                point = CatchmentPoint.objects.get(id=point_id)
            except:
                continue
        else:
            point = point_data
            point_id = point.id
        
        # Analizar coherencia
        analisis = analyze_data_coherence(point_id, days_back=30)
        
        if 'error' in analisis:
            elements.append(Paragraph(f"<b>Punto: {analisis.get('point_name', point_id)}</b>", heading_style))
            elements.append(Paragraph(f"Error: {analisis['error']}", styles['Normal']))
            elements.append(Spacer(1, 0.3*inch))
            continue
        
        # Encabezado del punto
        elements.append(Paragraph(f"<b>Punto de Captación: {analisis['point_name']}</b>", heading_style))
        if analisis.get('project'):
            elements.append(Paragraph(f"Proyecto: {analisis['project']}", styles['Normal']))
        elements.append(Paragraph(f"Período analizado: {analisis['periodo']['inicio']} a {analisis['periodo']['fin']} ({analisis['periodo']['dias']} días)", styles['Normal']))
        elements.append(Paragraph(f"Total de mediciones: {format_number_with_thousands(analisis['total_registros'])}", styles['Normal']))
        elements.append(Spacer(1, 0.2*inch))
        
        # ========================================
        # SECCIÓN: CONFIGURACIÓN
        # ========================================
        elements.append(Paragraph("<b>CONFIGURACIÓN</b>", heading_style))
        elements.append(Spacer(1, 0.1*inch))
        
        config = analisis.get('configuracion', {})
        
        # Variables configuradas con detalles (sin columna Servicio, tablas mejoradas con ajuste de texto)
        if config.get('variables'):
            elements.append(Paragraph("<b>Variables Configuradas:</b>", styles['Heading3']))
            vars_data = []
            # Encabezados con Paragraph para mejor control
            vars_data.append([
                Paragraph('<b>Nombre</b>', styles['Normal']),
                Paragraph('<b>Tipo</b>', styles['Normal']),
                Paragraph('<b>Factor Pulsos</b>', styles['Normal']),
                Paragraph('<b>Función</b>', styles['Normal'])
            ])
            for var in config['variables']:
                funcion_text = var.get('funcion', 'Sin registros')
                # Usar Paragraph para permitir ajuste automático de texto
                vars_data.append([
                    Paragraph(str(var.get('nombre', 'Sin registros')), styles['Normal']),
                    Paragraph(str(var.get('tipo', 'Sin registros')), styles['Normal']),
                    Paragraph(str(format_number_with_thousands(var.get('pulses_factor')) if var.get('pulses_factor') else 'Sin registros'), styles['Normal']),
                    Paragraph(funcion_text, styles['Normal'])
                ])
            
            vars_table = Table(vars_data, colWidths=[1.3*inch, 1.1*inch, 1.1*inch, 2.2*inch])
            vars_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [water_light_blue, colors.white]),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(vars_table)
            elements.append(Spacer(1, 0.2*inch))
        
        # Perfil de datos (datos estáticos) con ajuste de texto
        if config.get('perfil'):
            perfil = config['perfil']
            elements.append(Paragraph("<b>Datos Estáticos del Perfil:</b>", styles['Heading3']))
            perfil_data = []
            perfil_data.append([
                Paragraph('<b>Parámetro</b>', styles['Normal']),
                Paragraph('<b>Valor</b>', styles['Normal']),
                Paragraph('<b>Descripción</b>', styles['Normal'])
            ])
            perfil_rows = [
                ['d1 - Profundidad', f"{perfil.get('d1_profundidad', 'Sin registros')} m" if perfil.get('d1_profundidad') else 'Sin registros', 'Profundidad total del pozo'],
                ['d2 - Posicionamiento Bomba', f"{perfil.get('d2_posicionamiento_bomba', 'Sin registros')} m" if perfil.get('d2_posicionamiento_bomba') else 'Sin registros', 'Posición de la bomba'],
                ['d3 - Posicionamiento Nivel', f"{perfil.get('d3_posicionamiento_nivel', 'Sin registros')} m" if perfil.get('d3_posicionamiento_nivel') else 'Sin registros', 'Posición del sensor de nivel'],
                ['d4 - Diámetro Ducto Salida', f"{perfil.get('d4_diametro_ducto_salida', 'Sin registros')} pulg" if perfil.get('d4_diametro_ducto_salida') else 'Sin registros', 'Diámetro del ducto de salida'],
                ['d5 - Diámetro Flujómetro', f"{perfil.get('d5_diametro_flujometro', 'Sin registros')} pulg" if perfil.get('d5_diametro_flujometro') else 'Sin registros', 'Diámetro del flujómetro (para caudal probable)'],
                ['d6 - Caudalímetro Inicial', str(perfil.get('d6_caudalimetro_inicial', 'Sin registros')) if perfil.get('d6_caudalimetro_inicial') else 'Sin registros', 'Valor inicial del caudalímetro'],
                ['Fecha Inicio Telemetría', perfil.get('fecha_inicio_telemetria', 'Sin registros'), 'Fecha de inicio de telemetría'],
                ['Fecha Acta Entrega', perfil.get('fecha_acta_entrega', 'Sin registros'), 'Fecha del acta de entrega'],
                ['Telemetría Activa', 'Sí' if perfil.get('telemetria_activa') else 'No', 'Estado de la telemetría'],
            ]
            for row in perfil_rows:
                perfil_data.append([
                    Paragraph(str(row[0]), styles['Normal']),
                    Paragraph(str(row[1]), styles['Normal']),
                    Paragraph(str(row[2]), styles['Normal'])
                ])
            perfil_table = Table(perfil_data, colWidths=[1.9*inch, 1.4*inch, 2.0*inch])
            perfil_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [water_light_blue, colors.white]),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(perfil_table)
            elements.append(Spacer(1, 0.2*inch))
        
        # Frecuencia
        if config.get('frecuencia'):
            elements.append(Paragraph(f"<b>Frecuencia de Lectura:</b> {config['frecuencia']}", styles['Heading3']))
            elements.append(Spacer(1, 0.1*inch))
        
        elements.append(PageBreak())
        
        # ========================================
        # SECCIÓN: CONFIGURACIÓN DGA (PÁGINA SEPARADA)
        # ========================================
        if config.get('dga'):
            dga = config['dga']
            elements.append(Paragraph("<b>CONFIGURACIÓN DGA</b>", heading_style))
            elements.append(Paragraph(f"<b>Punto de Captación:</b> {analisis['point_name']}", styles['Normal']))
            elements.append(Spacer(1, 0.2*inch))
            
            dga_data = []
            dga_data.append([
                Paragraph('<b>Parámetro</b>', styles['Normal']),
                Paragraph('<b>Valor</b>', styles['Normal'])
            ])
            dga_rows = [
                ['Enviar a DGA', 'Sí' if dga.get('enviar_dga') else 'No'],
                ['Estándar', dga.get('estandar', 'Sin registros')],
                ['Tipo DGA', dga.get('tipo_dga', 'Sin registros')],
                ['Código Obra', dga.get('codigo_obra', 'Sin registros')],
                ['Caudal Otorgado', f"{format_decimal(dga.get('caudal_otorgado'), 2)} L/s" if dga.get('caudal_otorgado') else 'Sin registros'],
                ['Total Otorgado', f"{format_number_with_thousands(dga.get('total_otorgado'))} m³" if dga.get('total_otorgado') else 'Sin registros'],
                ['SHAC', dga.get('shac', 'Sin registros')],
                ['DGA Región', dga.get('region_dga', 'Sin registros')],
                ['Fecha Inicio Cumplimiento', dga.get('fecha_inicio_cumplimiento', 'Sin registros')],
                ['Fecha Creación Código', dga.get('fecha_creacion_codigo', 'Sin registros')],
                ['Nombre Informante', dga.get('nombre_informante', 'Sin registros')],
                ['RUT Informante', dga.get('rut_informante', 'Sin registros')],
            ]
            for row in dga_rows:
                dga_data.append([
                    Paragraph(str(row[0]), styles['Normal']),
                    Paragraph(str(row[1]), styles['Normal'])
                ])
            dga_table = Table(dga_data, colWidths=[2.3*inch, 3.0*inch])
            dga_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [water_light_blue, colors.white]),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(dga_table)
            elements.append(Spacer(1, 0.2*inch))
            
            elements.append(PageBreak())
        
        # ========================================
        # SECCIÓN: TELEMETRÍA DEL DÍA (PÁGINA SEPARADA)
        # ========================================
        if analisis.get('telemetria_dia'):
            td = analisis['telemetria_dia']
            elements.append(Paragraph("<b>TELEMETRÍA DEL DÍA</b>", heading_style))
            elements.append(Paragraph(f"<b>Punto de Captación:</b> {analisis['point_name']}", styles['Normal']))
            elements.append(Paragraph(f"<b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
            elements.append(Spacer(1, 0.2*inch))
            
            dia_data = [
                ['Indicador', 'Valor'],
                ['Mediciones del día', format_number_with_thousands(td['total_registros'])],
                ['Consumo total del día', f"{format_number_with_thousands(int(td['consumo_total']))} m³"],
                ['Caudal promedio del día', f"{format_decimal(td['caudal_promedio'], 2)} L/s"],
                ['Nivel promedio del día', f"{format_decimal(td['nivel_promedio'], 2)} m"]
            ]
            dia_table = Table(dia_data, colWidths=[2.2*inch, 1.8*inch])
            dia_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(dia_table)
            elements.append(Spacer(1, 0.2*inch))
            
            elements.append(PageBreak())
        
        # ========================================
        # SECCIÓN: ANÁLISIS DE DATOS CON GRÁFICOS
        # ========================================
        elements.append(Paragraph("<b>ANÁLISIS DE DATOS DEL PERÍODO</b>", heading_style))
        elements.append(Paragraph(
            f"<i>Esta sección presenta un análisis detallado de las tres variables principales (Total, Caudal y Nivel) "
            f"durante el período analizado ({analisis['periodo']['inicio']} a {analisis['periodo']['fin']}). "
            f"Los gráficos muestran la evolución temporal de cada variable para facilitar la identificación de patrones y anomalías.</i>",
            natural_text_style
        ))
        elements.append(Spacer(1, 0.15*inch))
        
        # Obtener registros del período para los gráficos
        from api.core.models import InteractionDetail, Variable
        from datetime import timedelta
        import pytz
        
        # Verificar qué variables tiene el punto
        variables = Variable.objects.filter(scheme_catchment__points_catchment_id=point_id)
        has_totalizado = variables.filter(type_variable="TOTALIZADO").exists()
        has_caudal = variables.filter(type_variable__in=["CAUDAL", "CAUDAL_PROMEDIO"]).exists()
        has_nivel = variables.filter(type_variable="NIVEL").exists()
        
        chile_tz = pytz.timezone("America/Santiago")
        periodo_inicio = datetime.strptime(analisis['periodo']['inicio'], '%Y-%m-%d')
        periodo_fin = datetime.strptime(analisis['periodo']['fin'], '%Y-%m-%d')
        periodo_inicio = chile_tz.localize(periodo_inicio)
        periodo_fin = chile_tz.localize(periodo_fin) + timedelta(days=1)
        
        chart_records = InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=periodo_inicio,
            date_time_medition__lte=periodo_fin
        ).order_by('date_time_medition')
        
        # Preparar datos para gráficos
        total_data = []
        caudal_data = []
        nivel_data = []
        dates_labels = []
        
        for record in chart_records:
            if record.date_time_medition:
                dates_labels.append(record.date_time_medition.strftime('%Y-%m-%d %H:%M'))
                if record.total:
                    total_data.append(float(record.total))
                else:
                    total_data.append(None)
                
                if record.flow:
                    caudal_data.append(float(record.flow))
                else:
                    caudal_data.append(None)
                
                if record.nivel:
                    nivel_data.append(float(record.nivel))
                else:
                    nivel_data.append(None)
        
        # Crear gráficos si hay datos
        if chart_records.exists():
            elements.append(Paragraph("<b>Gráficos de Evolución Temporal</b>", styles['Heading3']))
            elements.append(Spacer(1, 0.1*inch))
            
            # Gráfico de Total
            if has_totalizado and any(t is not None for t in total_data):
                total_clean = [t for t in total_data if t is not None]
                if total_clean:
                    elements.append(Paragraph("<b>Total Acumulado (m³)</b>", styles['Normal']))
                    elements.append(Paragraph(
                        "<i>Muestra la evolución del total acumulado durante el período. "
                        "Este valor siempre debe crecer o mantenerse constante.</i>",
                        natural_text_style
                    ))
                    total_chart = create_line_chart(
                        total_clean, 
                        f"Total Acumulado - {analisis['point_name']}", 
                        "m³",
                        '#0066CC',
                        width=500,
                        height=200
                    )
                    elements.append(total_chart)
                    elements.append(Spacer(1, 0.2*inch))
            
            # Gráfico de Caudal
            if has_caudal and any(c is not None and c > 0 for c in caudal_data):
                caudal_clean = [c for c in caudal_data if c is not None and c > 0]
                if caudal_clean:
                    elements.append(Paragraph("<b>Caudal (L/s)</b>", styles['Normal']))
                    elements.append(Paragraph(
                        "<i>Muestra la evolución del caudal durante el período. "
                        "Valores cero indican ausencia de flujo o problemas en la medición.</i>",
                        natural_text_style
                    ))
                    caudal_chart = create_line_chart(
                        caudal_clean,
                        f"Caudal - {analisis['point_name']}",
                        "L/s",
                        '#00CC66',
                        width=500,
                        height=200
                    )
                    elements.append(caudal_chart)
                    elements.append(Spacer(1, 0.2*inch))
            
            # Gráfico de Nivel
            if has_nivel and any(n is not None for n in nivel_data):
                nivel_clean = [n for n in nivel_data if n is not None]
                if nivel_clean:
                    elements.append(Paragraph("<b>Nivel de Agua (m)</b>", styles['Normal']))
                    elements.append(Paragraph(
                        "<i>Muestra la evolución del nivel de agua durante el período. "
                        "Variaciones significativas pueden indicar cambios en el nivel freático o problemas de medición.</i>",
                        natural_text_style
                    ))
                    nivel_chart = create_line_chart(
                        nivel_clean,
                        f"Nivel - {analisis['point_name']}",
                        "m",
                        '#FF6600',
                        width=500,
                        height=200
                    )
                    elements.append(nivel_chart)
                    elements.append(Spacer(1, 0.2*inch))
            
            elements.append(PageBreak())
        
        # ========================================
        # SECCIÓN: ESTADÍSTICAS DETALLADAS
        # ========================================
        elements.append(Paragraph("<b>ESTADÍSTICAS DETALLADAS</b>", heading_style))
        elements.append(Paragraph(
            "<i>Las siguientes tablas presentan estadísticas resumidas de cada variable, "
            "incluyendo valores mínimos, máximos, promedios y variación porcentual.</i>",
            natural_text_style
        ))
        elements.append(Spacer(1, 0.15*inch))
        
        # Totalizado (siempre en entero, no tiene min/max porque siempre crece)
        if analisis.get('estadisticas', {}).get('total'):
            t = analisis['estadisticas']['total']
            elements.append(Paragraph("<b>Totalizado:</b>", styles['Heading3']))
            primer_total = analisis.get('primer_total_anio', {})
            primer_valor = primer_total.get('valor') if primer_total else None
            primer_fecha = primer_total.get('fecha', 'Sin registros') if primer_total else 'Sin registros'
            
            total_data = []
            total_data.append([
                Paragraph('<b>Indicador</b>', styles['Normal']),
                Paragraph('<b>Valor</b>', styles['Normal'])
            ])
            total_rows = [
                ['Total Actual', f"{format_number_with_thousands(int(t['max']))} m³"],
                ['Primer Registro del Año', f"{format_number_with_thousands(primer_valor)} m³" if primer_valor else 'Sin registros'],
                ['Fecha Primer Registro', primer_fecha if primer_fecha != 'N/A' else 'Sin registros'],
                ['Total Promedio', f"{format_number_with_thousands(int(t['promedio']))} m³"],
                ['NOTA', 'El total siempre crece (no tiene máximo). Se muestra el valor actual y el primer registro del año.'],
            ]
            for row in total_rows:
                total_data.append([
                    Paragraph(str(row[0]), styles['Normal']),
                    Paragraph(str(row[1]), styles['Normal'])
                ])
            total_table = Table(total_data, colWidths=[2.2*inch, 3.1*inch])
            total_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [water_light_blue, colors.white]),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(total_table)
            elements.append(Spacer(1, 0.2*inch))
        
        # Estadísticas básicas (sin total, ya que se muestra arriba) - Sin registros con caudal 0, variación como %
        if analisis.get('estadisticas'):
            elements.append(Paragraph("<b>Estadísticas de Caudal y Nivel:</b>", styles['Heading3']))
            elements.append(Paragraph(
                "<i>Esta tabla muestra los valores estadísticos principales de caudal y nivel durante el período analizado. "
                "La columna 'Variación %' indica el porcentaje de variación entre el mínimo y máximo, "
                "con colores: verde (< 30%) indica estabilidad, amarillo (≥ 30%) indica variación significativa.</i>",
                natural_text_style
            ))
            elements.append(Spacer(1, 0.1*inch))
            
            stats_data = []
            stats_data.append([
                Paragraph('<b>Métrica</b>', styles['Normal']),
                Paragraph('<b>Mínimo</b>', styles['Normal']),
                Paragraph('<b>Máximo</b>', styles['Normal']),
                Paragraph('<b>Promedio</b>', styles['Normal']),
                Paragraph('<b>Variación %</b>', styles['Normal'])
            ])
            
            row_idx = 1
            if 'caudal' in analisis['estadisticas']:
                c = analisis['estadisticas']['caudal']
                # Filtrar registros con caudal 0 para estadísticas
                min_caudal = c['min'] if c['min'] > 0 else None
                max_caudal = c['max'] if c['max'] > 0 else None
                variacion_caudal = calculate_variation_percentage(min_caudal, max_caudal)
                variacion_text = f"{variacion_caudal:.1f}%" if variacion_caudal is not None else 'Sin registros'
                
                stats_data.append([
                    Paragraph('Caudal (L/s)', styles['Normal']),
                    Paragraph(format_decimal(min_caudal, 2) if min_caudal else 'Sin registros', styles['Normal']),
                    Paragraph(format_decimal(max_caudal, 2) if max_caudal else 'Sin registros', styles['Normal']),
                    Paragraph(format_decimal(c['promedio'], 2), styles['Normal']),
                    Paragraph(variacion_text, styles['Normal'])
                ])
                row_idx += 1
            
            if 'nivel' in analisis['estadisticas']:
                n = analisis['estadisticas']['nivel']
                variacion_nivel = calculate_variation_percentage(n['min'], n['max'])
                variacion_nivel_text = f"{variacion_nivel:.1f}%" if variacion_nivel is not None else 'Sin registros'
                
                stats_data.append([
                    Paragraph('Nivel (m)', styles['Normal']),
                    Paragraph(format_decimal(n['min'], 2), styles['Normal']),
                    Paragraph(format_decimal(n['max'], 2), styles['Normal']),
                    Paragraph(format_decimal(n['promedio'], 2), styles['Normal']),
                    Paragraph(variacion_nivel_text, styles['Normal'])
                ])
                row_idx += 1
            
            if len(stats_data) > 1:
                stats_table = Table(stats_data, colWidths=[1.3*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch])
                # Crear estilo con colores según variación
                table_style = [
                    ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('TOPPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [water_light_blue, colors.white]),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ]
                
                # Agregar color de fondo a la columna de variación según el valor
                if 'caudal' in analisis['estadisticas']:
                    variacion_caudal = calculate_variation_percentage(
                        analisis['estadisticas']['caudal']['min'] if analisis['estadisticas']['caudal']['min'] > 0 else None,
                        analisis['estadisticas']['caudal']['max'] if analisis['estadisticas']['caudal']['max'] > 0 else None
                    )
                    if variacion_caudal is not None:
                        color_caudal = get_variation_color(variacion_caudal)
                        table_style.append(('BACKGROUND', (4, 1), (4, 1), color_caudal))
                
                if 'nivel' in analisis['estadisticas']:
                    variacion_nivel = calculate_variation_percentage(
                        analisis['estadisticas']['nivel']['min'],
                        analisis['estadisticas']['nivel']['max']
                    )
                    if variacion_nivel is not None:
                        color_nivel = get_variation_color(variacion_nivel)
                        table_style.append(('BACKGROUND', (4, 2), (4, 2), color_nivel))
                
                stats_table.setStyle(TableStyle(table_style))
                elements.append(stats_table)
                elements.append(Spacer(1, 0.2*inch))
        
        # Análisis avanzado
        elements.append(Paragraph("<b>Análisis Avanzado:</b>", styles['Heading3']))
        advanced_data = []
        
        # Pulsos 0
        if analisis.get('estadisticas', {}).get('pulses'):
            p = analisis['estadisticas']['pulses']
            advanced_data.append(['Pulsos recibidos', f"Total: {p['total']}, Ceros: {p['ceros']} ({p['porcentaje_ceros']:.1f}%)"])
        
        # Máximo nivel freático
        if analisis.get('estadisticas', {}).get('water_table'):
            wt = analisis['estadisticas']['water_table']
            advanced_data.append(['Máximo nivel freático', f"{wt['max']:.2f} m ({wt['max_date']})"])
        
        # Extremos de caudal con nivel
        if analisis.get('estadisticas', {}).get('caudal_extremos'):
            ce = analisis['estadisticas']['caudal_extremos']
            advanced_data.append(['Caudal mínimo', f"{ce['min']['valor']:.2f} L/s (Nivel: {ce['min']['nivel']:.2f} m) - {ce['min']['fecha']}"])
            advanced_data.append(['Caudal máximo', f"{ce['max']['valor']:.2f} L/s (Nivel: {ce['max']['nivel']:.2f} m) - {ce['max']['fecha']}"])
        
        # Máximo consumo por hora (total_diff)
        if analisis.get('max_consumo_hora'):
            mch = analisis['max_consumo_hora']
            advanced_data.append(['Máximo consumo por hora', f"{mch['valor']} m³/h ({mch['fecha']})"])
            if mch.get('fecha_logger'):
                advanced_data.append(['', f"Fecha Logger: {mch['fecha_logger']}"])
        
        # Totalizado año pasado
        if analisis.get('estadisticas', {}).get('totalizado_anio_pasado'):
            tap = analisis['estadisticas']['totalizado_anio_pasado']
            advanced_data.append(['Totalizado año pasado', f"{int(tap['valor'])} m³ ({tap['periodo']})"])
        
        # Variables PO (Pulsos Originales)
        if analisis.get('variables', {}).get('pulses_factor'):
            advanced_data.append(['Factor de pulsos (PO)', f"{analisis['variables']['pulses_factor']}"])
        
        if advanced_data:
            advanced_table = Table([['Indicador', 'Valor']] + advanced_data, colWidths=[2.2*inch, 3.1*inch])
            advanced_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(advanced_table)
            elements.append(Spacer(1, 0.2*inch))
        
        
        # Pulsos Procesados (no recibidos directamente)
        if analisis.get('pulsos_procesados'):
            elements.append(Paragraph("<b>Pulsos Procesados (últimos 10 registros):</b>", styles['Heading3']))
            elements.append(Paragraph("NOTA: Fórmula directa: total (m³) = (pulsos × pulses_factor) ÷ 1000. Fórmula inversa: pulsos procesados = (total × 1000) ÷ pulses_factor", natural_text_style))
            pulsos_data = [['Fecha', 'Pulsos Recibidos', 'Pulsos Procesados', 'Total (m³)']]
            for pp in analisis['pulsos_procesados'][:10]:
                pulsos_data.append([
                    pp['fecha'],
                    str(pp['pulsos_recibidos']),
                    str(pp['pulsos_procesados']),
                    str(pp['total_m3'])
                ])
            pulsos_table = Table(pulsos_data, colWidths=[1.5*inch, 1.2*inch, 1.2*inch, 1.2*inch])
            pulsos_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            elements.append(pulsos_table)
            elements.append(Spacer(1, 0.2*inch))
        
        # Fechas cuando llegó 0 en pulsos
        if analisis.get('fechas_pulsos_cero'):
            elements.append(Paragraph("<b>Registros con Pulsos = 0:</b>", styles['Heading3']))
            fechas_cero_data = [['Fecha Medición', 'Fecha Logger', 'Total (m³)']]
            for fpc in analisis['fechas_pulsos_cero'][:10]:
                fechas_cero_data.append([
                    fpc['fecha'],
                    fpc['fecha_logger'],
                    str(fpc['total'])
                ])
            fechas_cero_table = Table(fechas_cero_data, colWidths=[1.8*inch, 1.8*inch, 0.9*inch])
            fechas_cero_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            elements.append(fechas_cero_table)
            elements.append(Spacer(1, 0.2*inch))
        
        # Nivel mínimo igual freático
        if analisis.get('nivel_minimo_igual_freatico'):
            elements.append(Paragraph("<b>Registros con Nivel = Nivel Freático:</b>", styles['Heading3']))
            nivel_igual_data = [['Fecha', 'Nivel (m)', 'Nivel Freático (m)']]
            for nmf in analisis['nivel_minimo_igual_freatico']:
                nivel_igual_data.append([
                    nmf['fecha'],
                    f"{nmf['nivel']:.2f}",
                    f"{nmf['freatico']:.2f}"
                ])
            nivel_igual_table = Table(nivel_igual_data, colWidths=[1.8*inch, 1.3*inch, 1.3*inch])
            nivel_igual_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            elements.append(nivel_igual_table)
            elements.append(Spacer(1, 0.2*inch))
        
        # Comparación Caudal Probable vs Real (con velocidades múltiples)
        if analisis.get('caudal_probable_info'):
            elements.append(Paragraph("<b>Comparación Caudal Probable vs Real:</b>", styles['Heading3']))
            primera_comp = analisis['caudal_probable_info'][0] if analisis['caudal_probable_info'] else None
            if primera_comp:
                tipo_diametro = primera_comp.get('tipo_diametro', 'Sin registros')
                diametro_val = primera_comp.get('diametro', 'Sin registros')
                elements.append(Paragraph(f"NOTA: El caudal probable se calcula usando {tipo_diametro} ({diametro_val} pulg) con diferentes velocidades (1.0, 1.5, 2.0, 2.5, 3.0, 3.5 m/s).", natural_text_style))
            
            # Tabla con velocidades múltiples
            comp_headers = ['Fecha', 'Caudal Real (L/s)', 'Caudal Prob. Dinámico', 'v=1.0 m/s', 'v=1.5 m/s', 'v=2.0 m/s', 'v=2.5 m/s', 'v=3.0 m/s', 'v=3.5 m/s']
            comp_data = [comp_headers]
            for comp in analisis['caudal_probable_info'][:5]:
                caudales_v = comp.get('caudales_por_velocidad', {})
                row = [
                    comp['fecha'],
                    f"{comp['caudal_real']:.2f}",
                    f"{comp.get('caudal_probable_dinamico', 0):.2f}",
                    f"{caudales_v.get('1.0', 0):.2f}",
                    f"{caudales_v.get('1.5', 0):.2f}",
                    f"{caudales_v.get('2.0', 0):.2f}",
                    f"{caudales_v.get('2.5', 0):.2f}",
                    f"{caudales_v.get('3.0', 0):.2f}",
                    f"{caudales_v.get('3.5', 0):.2f}",
                ]
                comp_data.append(row)
            
            comp_table = Table(comp_data, colWidths=[1.1*inch, 0.8*inch, 0.8*inch, 0.6*inch, 0.6*inch, 0.6*inch, 0.6*inch, 0.6*inch, 0.6*inch])
            comp_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 7),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [water_light_blue, colors.white]),
            ]))
            elements.append(comp_table)
            elements.append(Spacer(1, 0.2*inch))
        
        # Últimos 5 registros enviados a DGA
        from api.core.models import InteractionDetail
        dga_records = InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            send_dga=True
        ).order_by('-date_time_medition')[:5]
        
        if dga_records.exists():
            elements.append(Paragraph("<b>Últimos 5 Registros Enviados a DGA:</b>", styles['Heading3']))
            dga_reg_data = [['Fecha Medición', 'Fecha Logger', 'Total (m³)', 'Caudal (L/s)', 'Nivel (m)']]
            for dga_rec in dga_records:
                dga_reg_data.append([
                    dga_rec.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if dga_rec.date_time_medition else 'Sin registros',
                    dga_rec.date_time_last_logger.strftime('%Y-%m-%d %H:%M:%S') if dga_rec.date_time_last_logger else 'Sin registros',
                    format_number_with_thousands(int(float(dga_rec.total))) if dga_rec.total else '0',
                    format_decimal(dga_rec.flow, 2) if dga_rec.flow else '0.00',
                    format_decimal(dga_rec.nivel, 2) if dga_rec.nivel else '0.00',
                ])
            dga_reg_table = Table(dga_reg_data, colWidths=[1.3*inch, 1.3*inch, 0.9*inch, 0.9*inch, 0.9*inch])
            dga_reg_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0066CC')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#E6F2FF')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            elements.append(dga_reg_table)
            elements.append(Spacer(1, 0.2*inch))
        
        elements.append(PageBreak())
        
        # ========================================
        # SECCIÓN: INCIDENCIAS (PÁGINA SEPARADA)
        # ========================================
        if analisis.get('incidencias'):
            elements.append(Paragraph("<b>INCIDENCIAS DETECTADAS</b>", heading_style))
            elements.append(Paragraph(f"<b>Punto de Captación:</b> {analisis['point_name']}", styles['Normal']))
            elements.append(Paragraph("Las siguientes incidencias han sido detectadas durante el análisis de los datos de telemetría.", natural_text_style))
            elements.append(Spacer(1, 0.2*inch))
            
            # Resumen de incidencias con casitas de color (sin gráfico)
            summary_data = [
                ['Tipo', 'Cantidad'],
                ['Críticas', format_number_with_thousands(analisis['incidencias_criticas'])],
                ['Advertencias', format_number_with_thousands(analisis['incidencias_advertencia'])],
                ['Informativas', format_number_with_thousands(analisis['incidencias_info'])],
            ]
            summary_table = Table(summary_data, colWidths=[1.8*inch, 0.9*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), water_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (0, 1), colors.HexColor('#CC0000')),  # Críticas rojo
                ('BACKGROUND', (0, 2), (0, 2), colors.HexColor('#FF6600')),  # Advertencias naranja
                ('BACKGROUND', (0, 3), (0, 3), water_blue),  # Informativas azul
                ('BACKGROUND', (1, 1), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (1, 1), (-1, -1), [water_light_blue, colors.white]),
            ]))
            elements.append(summary_table)
            elements.append(Spacer(1, 0.2*inch))
            
            # Lista de incidencias
            for idx, incidencia in enumerate(analisis['incidencias'], 1):
                tipo_color = {
                    'CRITICA': colors.HexColor('#CC0000'),  # Rojo para críticas
                    'ADVERTENCIA': colors.HexColor('#FF6600'),  # Naranja para advertencias
                    'INFO': water_blue  # Azul para informativas
                }.get(incidencia['tipo'], colors.black)
                
                elements.append(Paragraph(f"<b>Incidencia #{idx}: {incidencia['tipo']}</b>", styles['Heading3']))
                inc_data = [
                    ['Descripción', incidencia['descripcion']],
                    ['Detalle', incidencia['detalle']]
                ]
                inc_table = Table(inc_data, colWidths=[1.3*inch, 4.0*inch])
                inc_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (0, 0), (0, -1), tipo_color),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('BACKGROUND', (0, 0), (0, -1), water_light_blue),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                elements.append(inc_table)
                elements.append(Spacer(1, 0.15*inch))
        else:
            elements.append(Paragraph("<b>✓ No se detectaron incidencias</b>", styles['Normal']))
            elements.append(Paragraph("Los datos analizados no presentan anomalías detectables.", natural_text_style))
        
        # ========================================
        # SECCIÓN: CONCLUSIONES Y RECOMENDACIONES
        # ========================================
        elements.append(PageBreak())
        elements.append(Paragraph("<b>CONCLUSIONES Y RECOMENDACIONES</b>", heading_style))
        elements.append(Paragraph(
            f"<i>Esta sección presenta un resumen ejecutivo del análisis realizado para el punto de captación {analisis['point_name']} "
            f"durante el período del {analisis['periodo']['inicio']} al {analisis['periodo']['fin']}.</i>",
            natural_text_style
        ))
        elements.append(Spacer(1, 0.2*inch))
        
        conclusiones_data = []
        
        # Resumen de mediciones
        total_mediciones = analisis.get('total_registros', 0)
        conclusiones_data.append([
            Paragraph('<b>Total de Mediciones Analizadas</b>', styles['Normal']),
            Paragraph(format_number_with_thousands(total_mediciones), styles['Normal'])
        ])
        
        # Resumen de estadísticas principales
        if analisis.get('estadisticas', {}).get('total'):
            t = analisis['estadisticas']['total']
            conclusiones_data.append([
                Paragraph('<b>Total Acumulado Actual</b>', styles['Normal']),
                Paragraph(f"{format_number_with_thousands(int(t['max']))} m³", styles['Normal'])
            ])
        
        if analisis.get('estadisticas', {}).get('caudal'):
            c = analisis['estadisticas']['caudal']
            min_caudal = c['min'] if c['min'] > 0 else None
            max_caudal = c['max'] if c['max'] > 0 else None
            if min_caudal and max_caudal:
                conclusiones_data.append([
                    Paragraph('<b>Rango de Caudal</b>', styles['Normal']),
                    Paragraph(f"{format_decimal(min_caudal, 2)} - {format_decimal(max_caudal, 2)} L/s", styles['Normal'])
                ])
        
        if analisis.get('estadisticas', {}).get('nivel'):
            n = analisis['estadisticas']['nivel']
            conclusiones_data.append([
                Paragraph('<b>Rango de Nivel</b>', styles['Normal']),
                Paragraph(f"{format_decimal(n['min'], 2)} - {format_decimal(n['max'], 2)} m", styles['Normal'])
            ])
        
        # Resumen de incidencias
        total_incidencias = analisis.get('incidencias_criticas', 0) + analisis.get('incidencias_advertencia', 0) + analisis.get('incidencias_info', 0)
        conclusiones_data.append([
            Paragraph('<b>Total de Incidencias Detectadas</b>', styles['Normal']),
            Paragraph(format_number_with_thousands(total_incidencias), styles['Normal'])
        ])
        
        if analisis.get('incidencias_criticas', 0) > 0:
            conclusiones_data.append([
                Paragraph('<b>Incidencias Críticas</b>', styles['Normal']),
                Paragraph(f"{format_number_with_thousands(analisis['incidencias_criticas'])} - Requieren atención inmediata", styles['Normal'])
            ])
        
        # Recomendaciones basadas en el análisis
        recomendaciones = []
        
        if analisis.get('estadisticas', {}).get('caudal', {}).get('valores_cero', 0) > total_mediciones * 0.5:
            recomendaciones.append("⚠️ Se detectó un alto porcentaje de registros con caudal cero. Se recomienda verificar el sensor de caudal.")
        
        if analisis.get('estadisticas', {}).get('total'):
            t = analisis['estadisticas']['total']
            if t['max'] == t['min'] and total_mediciones > 1:
                recomendaciones.append("⚠️ El total acumulado no ha variado durante el período. Se recomienda verificar el funcionamiento del contador.")
        
        variacion_caudal = None
        if analisis.get('estadisticas', {}).get('caudal'):
            c = analisis['estadisticas']['caudal']
            min_caudal = c['min'] if c['min'] > 0 else None
            max_caudal = c['max'] if c['max'] > 0 else None
            variacion_caudal = calculate_variation_percentage(min_caudal, max_caudal)
            if variacion_caudal and variacion_caudal > 50:
                recomendaciones.append("ℹ️ Se detectó una variación significativa en el caudal (>50%). Esto puede ser normal según el uso, pero se recomienda revisar.")
        
        if analisis.get('incidencias_criticas', 0) == 0 and analisis.get('incidencias_advertencia', 0) == 0:
            recomendaciones.append("✅ No se detectaron incidencias críticas o advertencias. El sistema está funcionando correctamente.")
        
        if recomendaciones:
            elements.append(Paragraph("<b>Recomendaciones:</b>", styles['Heading3']))
            for rec in recomendaciones:
                elements.append(Paragraph(f"• {rec}", natural_text_style))
            elements.append(Spacer(1, 0.15*inch))
        
        # Tabla de resumen
        if conclusiones_data:
            conclusiones_table = Table(conclusiones_data, colWidths=[3.0*inch, 2.1*inch])
            conclusiones_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), water_light_blue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(conclusiones_table)
        
        elements.append(PageBreak())
    
    # Generar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

