"""
Generador de Excel para análisis de telemetría
==============================================

Genera archivos Excel con análisis detallado de telemetría:
- Por proyecto: varios puntos con indicadores por página
- Por punto: detalle mensual en pestañas con indicadores
"""

from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.axis import DateAxis
from api.core.models import CatchmentPoint, InteractionDetail, Variable
from api.core.validators.telemetry_validator import analyze_data_coherence
from api.cronjobs.telemetry.controllers.flow import average_flow
import pytz


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


# Estilos comunes
HEADER_FILL = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(bold=True, size=14)
BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)


def generate_excel_by_project(points: List[CatchmentPoint], project_name: Optional[str] = None) -> BytesIO:
    """
    Generar Excel de análisis de telemetría por proyecto.
    Incluye resumen completo con todos los puntos e indicadores, y luego cada punto tiene su propia página.
    
    Args:
        points: Lista de puntos de captación
        project_name: Nombre del proyecto (opcional)
    
    Returns:
        BytesIO con el archivo Excel
    """
    wb = Workbook()
    wb.remove(wb.active)  # Remover hoja por defecto
    
    # ========================================
    # HOJA DE RESUMEN COMPLETO CON TODOS LOS PUNTOS
    # ========================================
    ws_summary = wb.create_sheet(title="Resumen Completo", index=0)
    ws_summary['A1'] = f"Resumen Completo - Análisis de Telemetría"
    if project_name:
        ws_summary['A1'] = f"Resumen Completo - {project_name}"
    ws_summary['A1'].font = TITLE_FONT
    ws_summary.merge_cells('A1:O1')
    
    row = 3
    ws_summary[f'A{row}'] = "Este resumen presenta todos los indicadores principales de todos los puntos de captación en una sola vista."
    ws_summary[f'A{row}'].font = Font(italic=True, size=10)
    row += 2
    
    # Encabezados del resumen completo
    summary_headers = [
        'Punto de Captación',
        'Total Mediciones',
        'Total Actual (m³)',
        'Primer Registro Año (m³)',
        'Caudal Min (L/s)',
        'Caudal Max (L/s)',
        'Caudal Promedio (L/s)',
        'Nivel Min (m)',
        'Nivel Max (m)',
        'Nivel Promedio (m)',
        'Variación Caudal %',
        'Variación Nivel %',
        'Incidencias Críticas',
        'Incidencias Advertencia',
        'Consumo Día (m³)'
    ]
    
    for col, header in enumerate(summary_headers, 1):
        cell = ws_summary.cell(row, col, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = BORDER
    row += 1
    
    # Llenar datos del resumen
    for point in points:
        analisis = analyze_data_coherence(point.id, days_back=30)
        
        if 'error' in analisis:
            ws_summary.cell(row, 1, point.title)
            ws_summary.cell(row, 2, 'Error en análisis')
            for col in range(1, len(summary_headers) + 1):
                ws_summary.cell(row, col).border = BORDER
            row += 1
            continue
        
        # Datos del resumen
        ws_summary.cell(row, 1, point.title)
        ws_summary.cell(row, 2, format_number_with_thousands(analisis.get('total_registros', 0)))
        
        # Total
        if analisis.get('estadisticas', {}).get('total'):
            t = analisis['estadisticas']['total']
            ws_summary.cell(row, 3, format_number_with_thousands(int(t['max'])))
            primer_total = analisis.get('primer_total_anio', {})
            if primer_total.get('valor'):
                ws_summary.cell(row, 4, format_number_with_thousands(primer_total['valor']))
            else:
                ws_summary.cell(row, 4, 'Sin registros')
        else:
            ws_summary.cell(row, 3, 'Sin registros')
            ws_summary.cell(row, 4, 'Sin registros')
        
        # Caudal
        if analisis.get('estadisticas', {}).get('caudal'):
            c = analisis['estadisticas']['caudal']
            min_caudal = c['min'] if c['min'] > 0 else None
            max_caudal = c['max'] if c['max'] > 0 else None
            ws_summary.cell(row, 5, format_decimal(min_caudal, 2) if min_caudal else 'Sin registros')
            ws_summary.cell(row, 6, format_decimal(max_caudal, 2) if max_caudal else 'Sin registros')
            ws_summary.cell(row, 7, format_decimal(c['promedio'], 2))
            variacion_caudal = calculate_variation_percentage(min_caudal, max_caudal)
            ws_summary.cell(row, 11, f"{variacion_caudal:.1f}%" if variacion_caudal is not None else 'Sin registros')
        else:
            for col in [5, 6, 7, 11]:
                ws_summary.cell(row, col, 'Sin registros')
        
        # Nivel
        if analisis.get('estadisticas', {}).get('nivel'):
            n = analisis['estadisticas']['nivel']
            ws_summary.cell(row, 8, format_decimal(n['min'], 2))
            ws_summary.cell(row, 9, format_decimal(n['max'], 2))
            ws_summary.cell(row, 10, format_decimal(n['promedio'], 2))
            variacion_nivel = calculate_variation_percentage(n['min'], n['max'])
            ws_summary.cell(row, 12, f"{variacion_nivel:.1f}%" if variacion_nivel is not None else 'Sin registros')
        else:
            for col in [8, 9, 10, 12]:
                ws_summary.cell(row, col, 'Sin registros')
        
        # Incidencias
        ws_summary.cell(row, 13, format_number_with_thousands(analisis.get('incidencias_criticas', 0)))
        ws_summary.cell(row, 14, format_number_with_thousands(analisis.get('incidencias_advertencia', 0)))
        
        # Consumo del día
        if analisis.get('telemetria_dia'):
            td = analisis['telemetria_dia']
            ws_summary.cell(row, 15, format_number_with_thousands(int(td['consumo_total'])))
        else:
            ws_summary.cell(row, 15, 'Sin registros')
        
        # Aplicar bordes
        for col in range(1, len(summary_headers) + 1):
            ws_summary.cell(row, col).border = BORDER
            ws_summary.cell(row, col).alignment = Alignment(horizontal='center', vertical='center')
        
        row += 1
    
    # Ajustar ancho de columnas automáticamente según el contenido
    for col in range(1, len(summary_headers) + 1):
        col_letter = get_column_letter(col)
        max_length = 0
        for row_idx in range(3, row):
            cell = ws_summary.cell(row_idx, col)
            if cell.value:
                cell_length = len(str(cell.value))
                if cell_length > max_length:
                    max_length = cell_length
        # Ajustar ancho con padding (mínimo 12, máximo 30)
        ws_summary.column_dimensions[col_letter].width = min(max(max_length + 2, 12), 30)
    
    # ========================================
    # HOJAS INDIVIDUALES POR PUNTO
    # ========================================
    for point in points:
        # Crear hoja para cada punto
        ws = wb.create_sheet(title=point.title[:31])  # Excel limita a 31 caracteres
        
        # Título
        ws['A1'] = f"Análisis de Telemetría - {point.title}"
        ws['A1'].font = TITLE_FONT
        ws.merge_cells('A1:F1')
        
        # Análisis de coherencia
        analisis = analyze_data_coherence(point.id, days_back=30)
        
        if 'error' in analisis:
            ws['A3'] = f"Error: {analisis['error']}"
            continue
        
        # Información básica
        row = 3
        ws[f'A{row}'] = "Información Básica"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        info_data = [
            ['Proyecto', analisis.get('project', 'Sin registros')],
            ['Período', f"{analisis['periodo']['inicio']} a {analisis['periodo']['fin']}"],
            ['Total mediciones', format_number_with_thousands(analisis['total_registros'])],
            ['Variables', analisis['variables']['tipo_caudal'] or 'Ninguno'],
        ]
        
        for info in info_data:
            ws[f'A{row}'] = info[0]
            ws[f'B{row}'] = info[1]
            ws[f'A{row}'].font = Font(bold=True)
            row += 1
        
        row += 1
        
        # Indicadores principales
        ws[f'A{row}'] = "Indicadores Principales"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        headers = ['Indicador', 'Valor', 'Detalle']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        indicators = []
        
        # Estadísticas básicas
        if analisis.get('estadisticas'):
            stats = analisis['estadisticas']
            
            # Total (siempre en entero, no min/max porque siempre crece)
            if 'total' in stats:
                t = stats['total']
                indicators.append(['Total Actual (m³)', format_number_with_thousands(int(t['max'])), 'El total siempre crece'])
                primer_total = analisis.get('primer_total_anio', {})
                if primer_total.get('valor'):
                    fecha_primer = primer_total.get('fecha', 'Sin registros')
                    indicators.append(['Primer Registro del Año', f"{format_number_with_thousands(primer_total['valor'])} m³", fecha_primer if fecha_primer != 'N/A' else 'Sin registros'])
            
            if 'caudal' in stats:
                c = stats['caudal']
                indicators.append(['Caudal (L/s)', f"Min: {c['min']:.2f}, Max: {c['max']:.2f}", f"Promedio: {c['promedio']:.2f}"])
            
            if 'nivel' in stats:
                n = stats['nivel']
                indicators.append(['Nivel (m)', f"Min: {n['min']:.2f}, Max: {n['max']:.2f}", f"Promedio: {n['promedio']:.2f}"])
            
            # Análisis avanzado
            if 'pulses' in stats:
                p = stats['pulses']
                indicators.append(['Pulsos 0', f"{p['ceros']} de {p['total']}", f"{p['porcentaje_ceros']:.1f}%"])
            
            if 'water_table' in stats:
                wt = stats['water_table']
                indicators.append(['Máx. Nivel Freático', f"{wt['max']:.2f} m", wt['max_date']])
            
            # Máximo consumo por hora (total_diff)
            if analisis.get('max_consumo_hora'):
                mch = analisis['max_consumo_hora']
                indicators.append(['Máx. Consumo por Hora', f"{mch['valor']} m³/h", mch['fecha']])
            
            if 'totalizado_anio_pasado' in stats:
                tap = stats['totalizado_anio_pasado']
                indicators.append(['Totalizado Año Pasado', f"{int(tap['valor'])} m³", tap['periodo']])
        
        # Telemetría del día
        if analisis.get('telemetria_dia'):
            td = analisis['telemetria_dia']
            indicators.append(['Telemetría del Día', f"{format_number_with_thousands(td['total_registros'])} mediciones", f"Consumo: {format_number_with_thousands(int(td['consumo_total']))} m³"])
        
        # Escribir indicadores
        for indicator in indicators:
            for col, value in enumerate(indicator, 1):
                cell = ws.cell(row, col, value)
                cell.border = BORDER
                if col == 1:
                    cell.font = Font(bold=True)
            row += 1
        
        row += 1
        
        # Detalle de registros recientes
        ws[f'A{row}'] = "Últimas Mediciones (Top 20)"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        records = InteractionDetail.objects.filter(
            catchment_point=point
        ).order_by('-date_time_medition')[:20]
        
        detail_headers = ['Fecha Medición', 'Fecha Logger', 'Total (m³)', 'Caudal (L/s)', 'Nivel (m)', 'Consumo (m³/h)', 'Pulsos']
        detail_start_row = row
        for col, header in enumerate(detail_headers, 1):
            cell = ws.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        for record in records:
            ws.cell(row, 1, record.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if record.date_time_medition else 'Sin registros')
            # Mejorar formato de Fecha Logger
            if record.date_time_last_logger:
                logger_date = record.date_time_last_logger.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger_date = 'Sin registros'
            ws.cell(row, 2, logger_date)
            ws.cell(row, 3, int(float(record.total)) if record.total else 0)  # Total siempre en entero
            ws.cell(row, 4, float(record.flow) if record.flow else 0)
            ws.cell(row, 5, float(record.nivel) if record.nivel else 0)
            ws.cell(row, 6, int(float(record.total_diff)) if record.total_diff else 0)  # Consumo por hora en entero
            ws.cell(row, 7, int(record.pulses) if record.pulses else 0)
            
            for col in range(1, 8):
                ws.cell(row, col).border = BORDER
            row += 1
        
        # Ajustar ancho de columnas automáticamente según el contenido del título y datos
        for col in range(1, len(detail_headers) + 1):
            col_letter = get_column_letter(col)
            # Calcular ancho basado en el título
            header_length = len(detail_headers[col - 1])
            max_length = header_length
            
            # Calcular ancho basado en los datos
            for row_idx in range(detail_start_row, row):
                cell = ws.cell(row_idx, col)
                if cell.value:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
            
            # Ajustar ancho con padding (mínimo 12, máximo 30)
            ws.column_dimensions[col_letter].width = min(max(max_length + 2, 12), 30)
    
    # Guardar en buffer
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def generate_excel_by_point(point: CatchmentPoint) -> BytesIO:
    """
    Generar Excel de análisis de telemetría por punto.
    Cada mes tiene su propia pestaña con indicadores y detalle.
    
    Args:
        point: Punto de captación
    
    Returns:
        BytesIO con el archivo Excel
    """
    wb = Workbook()
    wb.remove(wb.active)
    
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    
    # Obtener todos los registros del año actual
    year_start = datetime(now.year, 1, 1, tzinfo=chile_tz)
    records = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=year_start
    ).order_by('date_time_medition')
    
    if not records.exists():
        ws = wb.create_sheet(title="Sin Datos")
        ws['A1'] = "No hay datos para este punto"
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer
    
    # Agrupar por mes
    months_data = {}
    for record in records:
        if record.date_time_medition:
            month_key = record.date_time_medition.strftime('%Y-%m')
            if month_key not in months_data:
                months_data[month_key] = []
            months_data[month_key].append(record)
    
    # Obtener variables
    variables = Variable.objects.filter(scheme_catchment__points_catchment=point)
    has_totalizado = variables.filter(type_variable="TOTALIZADO").exists()
    has_caudal_promedio = variables.filter(type_variable="CAUDAL_PROMEDIO").exists()
    var_totalizado = variables.filter(type_variable="TOTALIZADO").first()
    pulses_factor = var_totalizado.pulses_factor if var_totalizado and var_totalizado.pulses_factor else 1000
    
    # Crear hoja de resumen anual
    ws_summary = wb.create_sheet(title="Resumen Anual", index=0)
    ws_summary['A1'] = f"Resumen Anual - {point.title} ({now.year})"
    ws_summary['A1'].font = TITLE_FONT
    ws_summary.merge_cells('A1:D1')
    
    # Información del Pozo y DGA
    profile = point.data_config_profiles.first()
    dga_config = point.dga_data_config_profiles.first()
    row = 3
    
    # Datos estáticos del pozo (con estilos como Indicadores del Mes)
    if profile:
        ws_summary[f'A{row}'] = "Datos Estáticos del Pozo"
        ws_summary[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        # Encabezados con estilo
        pozo_headers = ['Parámetro', 'Valor']
        for col, header in enumerate(pozo_headers, 1):
            cell = ws_summary.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        pozo_info = [
            ['d1 - Profundidad', f"{float(profile.d1)} m" if profile.d1 else 'Sin registros'],
            ['d2 - Posicionamiento Bomba', f"{float(profile.d2)} m" if profile.d2 else 'Sin registros'],
            ['d3 - Posicionamiento Nivel', f"{float(profile.d3)} m" if profile.d3 else 'Sin registros'],
            ['d4 - Diámetro Ducto Salida', f"{float(profile.d4)} pulg" if profile.d4 else 'Sin registros'],
            ['d5 - Diámetro Flujómetro', f"{float(profile.d5)} pulg" if profile.d5 else 'Sin registros'],
            ['d6 - Caudalímetro Inicial', str(profile.d6) if profile.d6 else 'Sin registros'],
            ['Fecha Inicio Telemetría', profile.date_start_telemetry.strftime('%Y-%m-%d') if profile.date_start_telemetry else 'Sin registros'],
            ['Fecha Acta Entrega', profile.date_delivery_act.strftime('%Y-%m-%d') if profile.date_delivery_act else 'Sin registros'],
            ['Telemetría Activa', 'Sí' if profile.is_telemetry else 'No'],
        ]
        
        for info in pozo_info:
            ws_summary.cell(row, 1, info[0]).font = Font(bold=True)
            ws_summary.cell(row, 2, info[1])
            for col in range(1, 3):
                ws_summary.cell(row, col).border = BORDER
                ws_summary.cell(row, col).alignment = Alignment(horizontal='left', vertical='center')
            row += 1
        
        row += 1
    
    # Información general DGA si está configurado
    if dga_config and dga_config.send_dga:
        ws_summary[f'A{row}'] = "Información General DGA"
        ws_summary[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        # Obtener el último voucher DGA del punto (n_voucher real)
        ultimo_voucher = InteractionDetail.objects.filter(
            catchment_point=point,
            n_voucher__isnull=False
        ).exclude(n_voucher__exact='').order_by('-date_time_medition').first()
        voucher_dga = ultimo_voucher.n_voucher if ultimo_voucher and ultimo_voucher.n_voucher else 'Sin registros'
        
        dga_info = [
            ['Estándar', dga_config.get_standard_display() if hasattr(dga_config, 'get_standard_display') else dga_config.standard],
            ['Tipo DGA', dga_config.get_type_dga_display() if hasattr(dga_config, 'get_type_dga_display') else dga_config.type_dga],
            ['Código Obra', dga_config.code_dga or 'Sin registros'],
            ['Caudal Otorgado', f"{format_decimal(dga_config.flow_granted_dga, 2)} L/s" if dga_config.flow_granted_dga else 'Sin registros'],
            ['Total Otorgado', f"{format_number_with_thousands(dga_config.total_granted_dga)} m³" if dga_config.total_granted_dga else 'Sin registros'],
            ['SHAC', dga_config.shac or 'Sin registros'],
            ['DGA Región', dga_config.region_dga or 'Sin registros'],
            ['Voucher DGA', voucher_dga],
        ]
        
        for info in dga_info:
            ws_summary[f'A{row}'] = info[0]
            ws_summary[f'B{row}'] = info[1]
            ws_summary[f'A{row}'].font = Font(bold=True)
            row += 1
        
        row += 1
    
    # Últimos 5 registros enviados a DGA
    dga_records = InteractionDetail.objects.filter(
        catchment_point=point,
        send_dga=True
    ).order_by('-date_time_medition')[:5]
    
    if dga_records.exists():
        ws_summary[f'A{row}'] = "Últimos 5 Registros Enviados a DGA"
        ws_summary[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        dga_headers = ['Fecha Medición', 'Fecha Logger', 'Total (m³)', 'Caudal (L/s)', 'Nivel (m)']
        for col, header in enumerate(dga_headers, 1):
            cell = ws_summary.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        for dga_rec in dga_records:
            ws_summary.cell(row, 1, dga_rec.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if dga_rec.date_time_medition else 'Sin registros')
            # Mejorar formato de Fecha Logger
            if dga_rec.date_time_last_logger:
                logger_date = dga_rec.date_time_last_logger.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger_date = 'Sin registros'
            ws_summary.cell(row, 2, logger_date)
            ws_summary.cell(row, 3, int(float(dga_rec.total)) if dga_rec.total else 0)
            ws_summary.cell(row, 4, float(dga_rec.flow) if dga_rec.flow else 0)
            ws_summary.cell(row, 5, float(dga_rec.nivel) if dga_rec.nivel else 0)
            
            for col in range(1, 6):
                ws_summary.cell(row, col).border = BORDER
            row += 1
        
        row += 1
    
    ws_summary[f'A{row}'] = "Indicadores del Año"
    ws_summary[f'A{row}'].font = Font(bold=True, size=12)
    row += 1
    
    # Calcular indicadores anuales
    all_flows = [float(r.flow) if r.flow else 0 for r in records if r.flow]
    all_niveles = [float(r.nivel) if r.nivel else 0 for r in records if r.nivel]
    all_consumos = [float(r.total_diff) if r.total_diff else 0 for r in records if r.total_diff]
    
    annual_indicators = [
        ['Total registros', len(records)],
        ['Consumo total año', f"{sum(all_consumos):.2f} m³"],
        ['Caudal promedio año', f"{sum(all_flows) / len(all_flows):.2f} L/s" if all_flows else "0.00 L/s"],
        ['Caudal máximo año', f"{max(all_flows):.2f} L/s" if all_flows else "0.00 L/s"],
        ['Caudal mínimo año', f"{min([f for f in all_flows if f > 0]):.2f} L/s" if any(f > 0 for f in all_flows) else "0.00 L/s"],
        ['Nivel promedio año', f"{sum(all_niveles) / len(all_niveles):.2f} m" if all_niveles else "0.00 m"],
        ['Nivel máximo año', f"{max(all_niveles):.2f} m" if all_niveles else "0.00 m"],
    ]
    
    headers = ['Indicador', 'Valor']
    for col, header in enumerate(headers, 1):
        cell = ws_summary.cell(row, col, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = BORDER
    row += 1
    
    for indicator in annual_indicators:
        ws_summary.cell(row, 1, indicator[0]).font = Font(bold=True)
        ws_summary.cell(row, 2, indicator[1])
        for col in range(1, 3):
            ws_summary.cell(row, col).border = BORDER
        row += 1
    
    # Ajustar ancho de columnas automáticamente según el contenido
    # Columnas A y B (información básica)
    ws_summary.column_dimensions['A'].width = 25
    ws_summary.column_dimensions['B'].width = 20
    
    # Ajustar ancho de columnas para tabla DGA si existe
    if dga_records.exists():
        dga_headers = ['Fecha Medición', 'Fecha Logger', 'Total (m³)', 'Caudal (L/s)', 'Nivel (m)']
        for col_idx, header in enumerate(dga_headers, 3):  # Empieza en columna C (3)
            col_letter = get_column_letter(col_idx)
            header_length = len(header)
            max_length = header_length
            
            # Calcular ancho basado en los datos (buscar desde la fila donde empieza la tabla DGA)
            dga_start_row = row - len(dga_records) - 1  # -1 para el header
            for row_idx in range(dga_start_row, row):
                cell = ws_summary.cell(row_idx, col_idx)
                if cell.value:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
            
            # Ajustar ancho con padding (mínimo 12, máximo 30)
            ws_summary.column_dimensions[col_letter].width = min(max(max_length + 2, 12), 30)
    
    # Crear hoja por mes
    month_names = {
        '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
        '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
        '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
    }
    
    for month_key in sorted(months_data.keys()):
        month_records = months_data[month_key]
        month_num = month_key.split('-')[1]
        month_name = month_names.get(month_num, month_key)
        ws = wb.create_sheet(title=f"{month_name} {month_key.split('-')[0]}")
        
        # Título
        ws['A1'] = f"{point.title} - {month_name} {month_key.split('-')[0]}"
        ws['A1'].font = TITLE_FONT
        ws.merge_cells('A1:G1')
        
        row = 3
        
        # Indicadores del mes
        ws[f'A{row}'] = "Indicadores del Mes"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        month_flows = [float(r.flow) if r.flow else 0 for r in month_records if r.flow]
        month_niveles = [float(r.nivel) if r.nivel else 0 for r in month_records if r.nivel]
        month_consumos = [float(r.total_diff) if r.total_diff else 0 for r in month_records if r.total_diff]
        
        month_indicators = [
            ['Total registros', len(month_records)],
            ['Consumo total mes', f"{sum(month_consumos):.2f} m³"],
            ['Caudal promedio mes', f"{sum(month_flows) / len(month_flows):.2f} L/s" if month_flows else "0.00 L/s"],
            ['Caudal máximo mes', f"{max(month_flows):.2f} L/s" if month_flows else "0.00 L/s"],
            ['Caudal mínimo mes', f"{min([f for f in month_flows if f > 0]):.2f} L/s" if any(f > 0 for f in month_flows) else "0.00 L/s"],
            ['Nivel promedio mes', f"{sum(month_niveles) / len(month_niveles):.2f} m" if month_niveles else "0.00 m"],
        ]
        
        headers = ['Indicador', 'Valor']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        for indicator in month_indicators:
            ws.cell(row, 1, indicator[0]).font = Font(bold=True)
            ws.cell(row, 2, indicator[1])
            for col in range(1, 3):
                ws.cell(row, col).border = BORDER
            row += 1
        
        row += 1
        
        # Últimos 5 registros enviados a DGA del mes
        month_dga_records = [r for r in month_records if r.send_dga][:5]
        if month_dga_records:
            ws[f'A{row}'] = f"Últimos 5 Registros Enviados a DGA - {month_name}"
            ws[f'A{row}'].font = Font(bold=True, size=12)
            row += 1
            
            dga_headers = ['Fecha Medición', 'Fecha Logger', 'Total (m³)', 'Caudal (L/s)', 'Nivel (m)']
            for col, header in enumerate(dga_headers, 1):
                cell = ws.cell(row, col, header)
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
                cell.alignment = Alignment(horizontal='center', vertical='center')
                cell.border = BORDER
            row += 1
            
            for dga_rec in month_dga_records:
                ws.cell(row, 1, dga_rec.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if dga_rec.date_time_medition else 'Sin registros')
                # Mejorar formato de Fecha Logger
                if dga_rec.date_time_last_logger:
                    logger_date = dga_rec.date_time_last_logger.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    logger_date = 'Sin registros'
                ws.cell(row, 2, logger_date)
                ws.cell(row, 3, int(float(dga_rec.total)) if dga_rec.total else 0)
                ws.cell(row, 4, float(dga_rec.flow) if dga_rec.flow else 0)
                ws.cell(row, 5, float(dga_rec.nivel) if dga_rec.nivel else 0)
                
                for col in range(1, 6):
                    ws.cell(row, col).border = BORDER
                row += 1
            
            row += 1
        
        # Detalle del mes
        ws[f'A{row}'] = "Detalle del Mes"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        detail_headers = ['Fecha Medición', 'Fecha Logger', 'Total (m³)', 'Caudal (L/s)', 'Nivel (m)', 'Consumo (m³/h)', 'Pulsos', 'Nivel Freático (m)']
        detail_start_row = row  # Guardar fila donde empieza el detalle para los gráficos
        for col, header in enumerate(detail_headers, 1):
            cell = ws.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        # Obtener perfil para verificar d5
        profile = point.data_config_profiles.first()
        
        for record in month_records:
            ws.cell(row, 1, record.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if record.date_time_medition else 'Sin registros')
            # Mejorar formato de Fecha Logger
            if record.date_time_last_logger:
                logger_date = record.date_time_last_logger.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger_date = 'Sin registros'
            ws.cell(row, 2, logger_date)
            ws.cell(row, 3, int(float(record.total)) if record.total else 0)  # Total siempre en entero
            
            # Calcular caudal probable si es CAUDAL_PROMEDIO y hay d5
            if has_caudal_promedio and profile and profile.d5 and record.total and record.date_time_medition:
                try:
                    point_dict = {"id": point.id}
                    total_actual = float(record.total)
                    curr_ts = record.date_time_medition
                    if curr_ts.tzinfo is None:
                        curr_ts = chile_tz.localize(curr_ts)
                    else:
                        curr_ts = curr_ts.astimezone(chile_tz)
                    caudal_probable = average_flow(point_dict, total_actual, curr_ts)
                    ws.cell(row, 4, caudal_probable)
                except:
                    ws.cell(row, 4, float(record.flow) if record.flow else 0)
            else:
                ws.cell(row, 4, float(record.flow) if record.flow else 0)
            
            ws.cell(row, 5, float(record.nivel) if record.nivel else 0)
            ws.cell(row, 6, float(record.total_diff) if record.total_diff else 0)  # Consumo por hora
            ws.cell(row, 7, int(record.pulses) if record.pulses else 0)
            ws.cell(row, 8, float(record.water_table) if record.water_table else 0)
            for col in range(1, 9):
                ws.cell(row, col).border = BORDER
            row += 1
        
        # Ajustar ancho de columnas automáticamente según el contenido del título y datos
        for col in range(1, len(detail_headers) + 1):
            col_letter = get_column_letter(col)
            # Calcular ancho basado en el título
            header_length = len(detail_headers[col - 1])
            max_length = header_length
            
            # Calcular ancho basado en los datos
            for row_idx in range(detail_start_row, row):
                cell = ws.cell(row_idx, col)
                if cell.value:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
            
            # Ajustar ancho con padding (mínimo 12, máximo 30)
            ws.column_dimensions[col_letter].width = min(max(max_length + 2, 12), 30)
        
        # Calcular columna donde empiezan los gráficos (después de la última columna de datos)
        chart_start_col = len(detail_headers) + 2  # +2 para dejar espacio
        chart_col_letter = get_column_letter(chart_start_col)
        
        # Agregar gráficos si hay datos (a la derecha después de la tabla)
        if month_records and len(month_records) > 1:
            # Gráfico de Caudal
            if has_caudal_promedio or any(r.flow for r in month_records if r.flow):
                chart_flow = LineChart()
                chart_flow.title = f"Caudal (L/s) - {month_name}"
                chart_flow.style = 10
                chart_flow.y_axis.title = 'Caudal (L/s)'
                chart_flow.x_axis.title = 'Registros'
                
                flow_col = 4  # Columna D
                data_flow = Reference(ws, min_col=flow_col, min_row=detail_start_row, max_row=row-1)
                chart_flow.add_data(data_flow, titles_from_data=False)
                chart_flow.series[0].graphicalProperties.line.solidFill = "0066CC"
                
                # Posicionar gráfico a la derecha después de la tabla
                ws.add_chart(chart_flow, f"{chart_col_letter}{detail_start_row}")
            
            # Gráfico de Nivel
            if any(r.nivel for r in month_records if r.nivel):
                chart_nivel = LineChart()
                chart_nivel.title = f"Nivel (m) - {month_name}"
                chart_nivel.style = 10
                chart_nivel.y_axis.title = 'Nivel (m)'
                chart_nivel.x_axis.title = 'Registros'
                
                nivel_col = 5  # Columna E
                data_nivel = Reference(ws, min_col=nivel_col, min_row=detail_start_row, max_row=row-1)
                chart_nivel.add_data(data_nivel, titles_from_data=False)
                chart_nivel.series[0].graphicalProperties.line.solidFill = "00CC66"
                
                # Posicionar gráfico debajo del anterior, a la derecha
                chart_row = detail_start_row + 15
                ws.add_chart(chart_nivel, f"{chart_col_letter}{chart_row}")
            
            # Gráfico de Total
            if has_totalizado and any(r.total for r in month_records if r.total):
                chart_total = LineChart()
                chart_total.title = f"Total (m³) - {month_name}"
                chart_total.style = 10
                chart_total.y_axis.title = 'Total (m³)'
                chart_total.x_axis.title = 'Registros'
                
                total_col = 3  # Columna C
                data_total = Reference(ws, min_col=total_col, min_row=detail_start_row, max_row=row-1)
                chart_total.add_data(data_total, titles_from_data=False)
                chart_total.series[0].graphicalProperties.line.solidFill = "FF6600"
                
                # Posicionar gráfico debajo del anterior, a la derecha
                chart_row = detail_start_row + 30
                ws.add_chart(chart_total, f"{chart_col_letter}{chart_row}")
    
    # Guardar en buffer
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def generate_excel_last_month_by_points(points: List[CatchmentPoint], project_name: Optional[str] = None) -> BytesIO:
    """
    Generar Excel del último mes completo para varios puntos.
    Cada punto tiene su propia pestaña y hay un resumen combinado.
    
    Args:
        points: Lista de puntos de captación
        project_name: Nombre del proyecto (opcional)
    
    Returns:
        BytesIO con el archivo Excel
    """
    wb = Workbook()
    wb.remove(wb.active)
    
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    
    # Calcular último mes completo
    # Si estamos en octubre, el último mes completo es octubre
    # Si estamos en noviembre, el último mes completo es octubre
    current_month = now.month
    current_year = now.year
    
    # Si estamos en el día 1, el último mes completo es el anterior
    if now.day == 1:
        if current_month == 1:
            last_month = 12
            last_month_year = current_year - 1
        else:
            last_month = current_month - 1
            last_month_year = current_year
    else:
        # Si no es día 1, el último mes completo es el mes actual
        last_month = current_month
        last_month_year = current_year
    
    # Fechas del último mes completo
    if last_month == 12:
        next_month = 1
        next_year = last_month_year + 1
    else:
        next_month = last_month + 1
        next_year = last_month_year
    
    month_start = datetime(last_month_year, last_month, 1, tzinfo=chile_tz)
    month_end = datetime(next_year, next_month, 1, tzinfo=chile_tz) - timedelta(seconds=1)
    
    month_names = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    month_name = month_names.get(last_month, f'Mes {last_month}')
    
    # ========================================
    # HOJA DE RESUMEN COMBINADO
    # ========================================
    ws_summary = wb.create_sheet(title="Resumen Combinado", index=0)
    ws_summary['A1'] = f"Resumen del Último Mes Completo - {month_name} {last_month_year}"
    if project_name:
        ws_summary['A1'] = f"Resumen del Último Mes Completo - {month_name} {last_month_year} - {project_name}"
    ws_summary['A1'].font = TITLE_FONT
    ws_summary.merge_cells('A1:F1')
    
    row = 3
    ws_summary[f'A{row}'] = f"Período: {month_start.strftime('%Y-%m-%d')} a {month_end.strftime('%Y-%m-%d')}"
    ws_summary[f'A{row}'].font = Font(bold=True, size=11)
    row += 1
    
    # Tabla resumen combinada de todos los puntos
    ws_summary[f'A{row}'] = "Resumen de Puntos de Captación"
    ws_summary[f'A{row}'].font = Font(bold=True, size=12)
    row += 1
    
    summary_headers = ['Punto', 'Total Mediciones', 'Consumo Total (m³)', 'Caudal Promedio (L/s)', 
                      'Caudal Máximo (L/s)', 'Nivel Promedio (m)', 'Total Actual (m³)']
    for col, header in enumerate(summary_headers, 1):
        cell = ws_summary.cell(row, col, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = BORDER
    row += 1
    
    # Análisis combinado
    all_analysis = []
    dga_warnings = []
    
    for point in points:
        # Obtener registros del mes
        month_records = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=month_start,
            date_time_medition__lte=month_end
        ).order_by('date_time_medition')
        
        if not month_records.exists():
            ws_summary.cell(row, 1, point.title)
            ws_summary.cell(row, 2, 'Sin datos')
            for col in range(1, 9):
                ws_summary.cell(row, col).border = BORDER
            row += 1
            continue
        
        # Análisis del punto
        analisis = analyze_data_coherence(point.id, days_back=30)
        all_analysis.append(analisis)
        
        # Calcular indicadores del mes
        month_flows = [float(r.flow) if r.flow else 0 for r in month_records if r.flow]
        month_niveles = [float(r.nivel) if r.nivel else 0 for r in month_records if r.nivel]
        month_consumos = [float(r.total_diff) if r.total_diff else 0 for r in month_records if r.total_diff]
        
        # Total actual
        last_record = month_records.order_by('-date_time_medition').first()
        total_actual = int(float(last_record.total)) if last_record and last_record.total else 0
        
        # Verificar límites DGA
        dga_config = point.dga_data_config_profiles.first()
        dga_warning = None
        if dga_config and dga_config.send_dga:
            if dga_config.flow_granted_dga:
                max_flow = max(month_flows) if month_flows else 0
                if max_flow > float(dga_config.flow_granted_dga):
                    dga_warning = f"⚠️ {point.title}: Caudal máximo {max_flow:.2f} L/s excede otorgado {float(dga_config.flow_granted_dga):.2f} L/s"
                    dga_warnings.append(dga_warning)
            
            if dga_config.total_granted_dga:
                if total_actual > int(dga_config.total_granted_dga):
                    dga_warning = f"⚠️ {point.title}: Total {total_actual} m³ excede otorgado {int(dga_config.total_granted_dga)} m³"
                    dga_warnings.append(dga_warning)
        
        # Escribir datos en resumen
        ws_summary.cell(row, 1, point.title)
        ws_summary.cell(row, 2, len(month_records))
        ws_summary.cell(row, 3, f"{sum(month_consumos):.2f}")
        ws_summary.cell(row, 4, f"{sum(month_flows) / len(month_flows):.2f}" if month_flows else "0.00")
        ws_summary.cell(row, 5, f"{max(month_flows):.2f}" if month_flows else "0.00")
        ws_summary.cell(row, 6, f"{sum(month_niveles) / len(month_niveles):.2f}" if month_niveles else "0.00")
        ws_summary.cell(row, 7, total_actual)
        for col in range(1, 8):
            ws_summary.cell(row, col).border = BORDER
        row += 1
    
    # Ajustar ancho de columnas del resumen automáticamente
    summary_headers_last_month = ['Punto', 'Total Mediciones', 'Consumo Total (m³)', 'Caudal Promedio (L/s)', 
                      'Caudal Máximo (L/s)', 'Nivel Promedio (m)', 'Total Actual (m³)']
    for col in range(1, len(summary_headers_last_month) + 1):
        col_letter = get_column_letter(col)
        header_length = len(summary_headers_last_month[col - 1])
        max_length = header_length
        
        # Calcular ancho basado en los datos
        for row_idx in range(3, row):
            cell = ws_summary.cell(row_idx, col)
            if cell.value:
                cell_length = len(str(cell.value))
                if cell_length > max_length:
                    max_length = cell_length
        
        # Ajustar ancho con padding (mínimo 12, máximo 30)
        ws_summary.column_dimensions[col_letter].width = min(max(max_length + 2, 12), 30)
    
    # Sección de análisis y comentarios
    row += 2
    ws_summary[f'A{row}'] = "Análisis y Comentarios"
    ws_summary[f'A{row}'].font = Font(bold=True, size=12)
    row += 1
    
    # Advertencias DGA
    if dga_warnings:
        ws_summary[f'A{row}'] = "⚠️ ADVERTENCIAS DGA - Límites Excedidos:"
        ws_summary[f'A{row}'].font = Font(bold=True, size=11, color="CC0000")
        row += 1
        for warning in dga_warnings:
            ws_summary[f'A{row}'] = warning
            ws_summary[f'A{row}'].font = Font(size=10, color="CC0000")
            row += 1
        row += 1
    
    # Resumen de incidencias por punto
    ws_summary[f'A{row}'] = "Resumen de Incidencias por Punto:"
    ws_summary[f'A{row}'].font = Font(bold=True, size=11)
    row += 1
    
    for analisis in all_analysis:
        if analisis.get('incidencias'):
            point_name = analisis.get('point_name', 'Sin registros')
            ws_summary[f'A{row}'] = f"• {point_name}:"
            ws_summary[f'A{row}'].font = Font(bold=True)
            row += 1
            
            if analisis.get('incidencias_criticas', 0) > 0:
                ws_summary[f'B{row}'] = f"  - Críticas: {analisis['incidencias_criticas']}"
                ws_summary[f'B{row}'].font = Font(size=10, color="CC0000")
                row += 1
            if analisis.get('incidencias_advertencia', 0) > 0:
                ws_summary[f'B{row}'] = f"  - Advertencias: {analisis['incidencias_advertencia']}"
                ws_summary[f'B{row}'].font = Font(size=10, color="FF6600")
                row += 1
    
    # ========================================
    # HOJAS POR PUNTO
    # ========================================
    variables_cache = {}
    
    for point in points:
        # Obtener registros del mes para este punto
        month_records = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=month_start,
            date_time_medition__lte=month_end
        ).order_by('date_time_medition')
        
        if not month_records.exists():
            continue
        
        # Crear hoja para el punto (limitar nombre a 31 caracteres)
        ws = wb.create_sheet(title=point.title[:31])
        
        # Título
        ws['A1'] = f"{point.title} - {month_name} {last_month_year}"
        ws['A1'].font = TITLE_FONT
        ws.merge_cells('A1:G1')
        
        row = 3
        
        # Datos estáticos del pozo (con estilos como Indicadores del Mes)
        profile = point.data_config_profiles.first()
        if profile:
            ws[f'A{row}'] = "Datos Estáticos del Pozo"
            ws[f'A{row}'].font = Font(bold=True, size=12)
            row += 1
            
            # Encabezados con estilo
            pozo_headers = ['Parámetro', 'Valor']
            for col, header in enumerate(pozo_headers, 1):
                cell = ws.cell(row, col, header)
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
                cell.alignment = Alignment(horizontal='center', vertical='center')
                cell.border = BORDER
            row += 1
            
            pozo_info = [
                ['d1 - Profundidad', f"{float(profile.d1)} m" if profile.d1 else 'Sin registros'],
                ['d2 - Posicionamiento Bomba', f"{float(profile.d2)} m" if profile.d2 else 'Sin registros'],
                ['d3 - Posicionamiento Nivel', f"{float(profile.d3)} m" if profile.d3 else 'Sin registros'],
                ['d4 - Diámetro Ducto Salida', f"{float(profile.d4)} pulg" if profile.d4 else 'Sin registros'],
                ['d5 - Diámetro Flujómetro', f"{float(profile.d5)} pulg" if profile.d5 else 'Sin registros'],
                ['d6 - Caudalímetro Inicial', str(profile.d6) if profile.d6 else 'Sin registros'],
            ]
            
            for info in pozo_info:
                ws.cell(row, 1, info[0]).font = Font(bold=True)
                ws.cell(row, 2, info[1])
                for col in range(1, 3):
                    ws.cell(row, col).border = BORDER
                    ws.cell(row, col).alignment = Alignment(horizontal='left', vertical='center')
                row += 1
            
            row += 1
        
        # Información DGA
        dga_config = point.dga_data_config_profiles.first()
        if dga_config and dga_config.send_dga:
            ws[f'A{row}'] = "Información DGA"
            ws[f'A{row}'].font = Font(bold=True, size=12)
            row += 1
            
            ultimo_voucher = InteractionDetail.objects.filter(
                catchment_point=point,
                n_voucher__isnull=False
            ).exclude(n_voucher__exact='').order_by('-date_time_medition').first()
            voucher_dga = ultimo_voucher.n_voucher if ultimo_voucher and ultimo_voucher.n_voucher else 'Sin registros'
            
            dga_info = [
                ['Estándar', dga_config.get_standard_display() if hasattr(dga_config, 'get_standard_display') else dga_config.standard],
                ['Tipo DGA', dga_config.get_type_dga_display() if hasattr(dga_config, 'get_type_dga_display') else dga_config.type_dga],
                ['Código Obra', dga_config.code_dga or 'Sin registros'],
                ['Caudal Otorgado', f"{format_decimal(dga_config.flow_granted_dga, 2)} L/s" if dga_config.flow_granted_dga else 'Sin registros'],
                ['Total Otorgado', f"{format_number_with_thousands(dga_config.total_granted_dga)} m³" if dga_config.total_granted_dga else 'Sin registros'],
                ['SHAC', dga_config.shac or 'Sin registros'],
                ['DGA Región', dga_config.region_dga or 'Sin registros'],
                ['Voucher DGA', voucher_dga],
            ]
            
            for info in dga_info:
                ws[f'A{row}'] = info[0]
                ws[f'B{row}'] = info[1]
                ws[f'A{row}'].font = Font(bold=True)
                row += 1
            
            row += 1
        
        # Indicadores del mes
        ws[f'A{row}'] = "Indicadores del Mes"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        month_flows = [float(r.flow) if r.flow else 0 for r in month_records if r.flow]
        month_niveles = [float(r.nivel) if r.nivel else 0 for r in month_records if r.nivel]
        month_consumos = [float(r.total_diff) if r.total_diff else 0 for r in month_records if r.total_diff]
        
        # Obtener variables
        if point.id not in variables_cache:
            variables_cache[point.id] = Variable.objects.filter(scheme_catchment__points_catchment=point)
        variables = variables_cache[point.id]
        has_totalizado = variables.filter(type_variable="TOTALIZADO").exists()
        has_caudal_promedio = variables.filter(type_variable="CAUDAL_PROMEDIO").exists()
        var_totalizado = variables.filter(type_variable="TOTALIZADO").first()
        
        month_indicators = [
            ['Total registros', len(month_records)],
            ['Consumo total mes', f"{sum(month_consumos):.2f} m³"],
            ['Caudal promedio mes', f"{sum(month_flows) / len(month_flows):.2f} L/s" if month_flows else "0.00 L/s"],
            ['Caudal máximo mes', f"{max(month_flows):.2f} L/s" if month_flows else "0.00 L/s"],
            ['Caudal mínimo mes', f"{min([f for f in month_flows if f > 0]):.2f} L/s" if any(f > 0 for f in month_flows) else "0.00 L/s"],
            ['Nivel promedio mes', f"{sum(month_niveles) / len(month_niveles):.2f} m" if month_niveles else "0.00 m"],
            ['Nivel máximo mes', f"{max(month_niveles):.2f} m" if month_niveles else "0.00 m"],
            ['Nivel mínimo mes', f"{min([n for n in month_niveles if n > 0]):.2f} m" if any(n > 0 for n in month_niveles) else "0.00 m"],
        ]
        
        if has_totalizado:
            last_record = month_records.order_by('-date_time_medition').first()
            total_actual = int(float(last_record.total)) if last_record and last_record.total else 0
            month_indicators.append(['Total Actual (m³)', f"{total_actual}"])
        
        headers = ['Indicador', 'Valor']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        for indicator in month_indicators:
            ws.cell(row, 1, indicator[0]).font = Font(bold=True)
            ws.cell(row, 2, indicator[1])
            for col in range(1, 3):
                ws.cell(row, col).border = BORDER
            row += 1
        
        row += 1
        
        # Detalle del mes
        ws[f'A{row}'] = "Detalle del Mes"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        detail_headers = ['Fecha Medición', 'Fecha Logger', 'Total (m³)', 'Caudal (L/s)', 'Nivel (m)', 'Consumo (m³/h)', 'Pulsos', 'Nivel Freático (m)']
        detail_start_row = row
        for col, header in enumerate(detail_headers, 1):
            cell = ws.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        for record in month_records:
            ws.cell(row, 1, record.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if record.date_time_medition else 'Sin registros')
            # Mejorar formato de Fecha Logger
            if record.date_time_last_logger:
                logger_date = record.date_time_last_logger.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger_date = 'Sin registros'
            ws.cell(row, 2, logger_date)
            ws.cell(row, 3, int(float(record.total)) if record.total else 0)
            
            # Calcular caudal probable si es CAUDAL_PROMEDIO
            if has_caudal_promedio and profile and profile.d5 and record.total and record.date_time_medition:
                try:
                    point_dict = {"id": point.id}
                    total_actual = float(record.total)
                    curr_ts = record.date_time_medition
                    if curr_ts.tzinfo is None:
                        curr_ts = chile_tz.localize(curr_ts)
                    else:
                        curr_ts = curr_ts.astimezone(chile_tz)
                    caudal_probable = average_flow(point_dict, total_actual, curr_ts)
                    ws.cell(row, 4, caudal_probable)
                except:
                    ws.cell(row, 4, float(record.flow) if record.flow else 0)
            else:
                ws.cell(row, 4, float(record.flow) if record.flow else 0)
            
            ws.cell(row, 5, float(record.nivel) if record.nivel else 0)
            ws.cell(row, 6, float(record.total_diff) if record.total_diff else 0)
            ws.cell(row, 7, int(record.pulses) if record.pulses else 0)
            ws.cell(row, 8, float(record.water_table) if record.water_table else 0)
            for col in range(1, 9):
                ws.cell(row, col).border = BORDER
            row += 1
        
        # Ajustar ancho de columnas automáticamente según el contenido del título y datos
        for col in range(1, len(detail_headers) + 1):
            col_letter = get_column_letter(col)
            # Calcular ancho basado en el título
            header_length = len(detail_headers[col - 1])
            max_length = header_length
            
            # Calcular ancho basado en los datos
            for row_idx in range(detail_start_row, row):
                cell = ws.cell(row_idx, col)
                if cell.value:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
            
            # Ajustar ancho con padding (mínimo 12, máximo 30)
            ws.column_dimensions[col_letter].width = min(max(max_length + 2, 12), 30)
        
        # Calcular columna donde empiezan los gráficos (después de la última columna de datos)
        chart_start_col = len(detail_headers) + 2  # +2 para dejar espacio
        chart_col_letter = get_column_letter(chart_start_col)
        
        # Agregar gráficos si hay datos (a la derecha después de la tabla)
        if month_records and len(month_records) > 1:
            # Gráfico de Caudal
            if has_caudal_promedio or any(r.flow for r in month_records if r.flow):
                chart_flow = LineChart()
                chart_flow.title = f"Caudal (L/s) - {month_name}"
                chart_flow.style = 10
                chart_flow.y_axis.title = 'Caudal (L/s)'
                chart_flow.x_axis.title = 'Registros'
                
                flow_col = 4
                data_flow = Reference(ws, min_col=flow_col, min_row=detail_start_row, max_row=row-1)
                chart_flow.add_data(data_flow, titles_from_data=False)
                chart_flow.series[0].graphicalProperties.line.solidFill = "0066CC"
                
                ws.add_chart(chart_flow, f"{chart_col_letter}{detail_start_row}")
            
            # Gráfico de Nivel
            if any(r.nivel for r in month_records if r.nivel):
                chart_nivel = LineChart()
                chart_nivel.title = f"Nivel (m) - {month_name}"
                chart_nivel.style = 10
                chart_nivel.y_axis.title = 'Nivel (m)'
                chart_nivel.x_axis.title = 'Registros'
                
                nivel_col = 5
                data_nivel = Reference(ws, min_col=nivel_col, min_row=detail_start_row, max_row=row-1)
                chart_nivel.add_data(data_nivel, titles_from_data=False)
                chart_nivel.series[0].graphicalProperties.line.solidFill = "00CC66"
                
                chart_row = detail_start_row + 15
                ws.add_chart(chart_nivel, f"{chart_col_letter}{chart_row}")
            
            # Gráfico de Total
            if has_totalizado and any(r.total for r in month_records if r.total):
                chart_total = LineChart()
                chart_total.title = f"Total (m³) - {month_name}"
                chart_total.style = 10
                chart_total.y_axis.title = 'Total (m³)'
                chart_total.x_axis.title = 'Registros'
                
                total_col = 3
                data_total = Reference(ws, min_col=total_col, min_row=detail_start_row, max_row=row-1)
                chart_total.add_data(data_total, titles_from_data=False)
                chart_total.series[0].graphicalProperties.line.solidFill = "FF6600"
                
                chart_row = detail_start_row + 30
                ws.add_chart(chart_total, f"{chart_col_letter}{chart_row}")
    
    # Guardar en buffer
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

