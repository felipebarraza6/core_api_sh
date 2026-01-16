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
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter
from django.db.models import Min, Max, Avg, Count, Sum

from api.core.models import CatchmentPoint, InteractionDetail, Variable
from api.core.validators.telemetry_validator import analyze_data_coherence
from api.cronjobs.telemetry.controllers.flow import average_flow

# Importar utilidades de los nuevos módulos
from .excel_utils import (
    HEADER_FILL, HEADER_FONT, TITLE_FONT, BORDER,
    format_number_with_thousands, format_decimal, calculate_variation_percentage,
    create_header_row, write_data_row, write_section_title, write_key_value_pair,
    auto_adjust_column_width
)
from .excel_writers import (
    write_pozo_info, write_dga_info, write_indicators_table,
    write_dga_records_table
)
from .excel_charts import add_month_charts
from .excel_data import (
    get_point_variables, get_months_with_data, get_month_statistics,
    calculate_month_consumo, calculate_flow_optimized,
    get_month_records_optimized, get_month_flows_sample
)
import pytz


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
    
    # Zona horaria de Chile
    chile_tz = pytz.timezone("America/Santiago")
    
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
        
        # Manejo seguro de datos
        periodo = analisis.get('periodo', {})
        periodo_text = f"{periodo.get('inicio', 'N/A')} a {periodo.get('fin', 'N/A')}" if periodo else 'Sin registros'
        variables = analisis.get('variables', {})
        tipo_caudal = variables.get('tipo_caudal', 'Ninguno') if variables else 'Ninguno'
        
        info_data = [
            ['Proyecto', analisis.get('project', 'Sin registros')],
            ['Período', periodo_text],
            ['Total mediciones', format_number_with_thousands(analisis.get('total_registros', 0))],
            ['Variables', tipo_caudal],
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
        
        detail_headers = ['ID', 'Fecha Medición', 'Fecha Logger', 'Total (m³)', 'Caudal (L/s)', 'Nivel (m)', 'Consumo (m³/h)', 'Pulsos', 'Voucher DGA']
        detail_start_row = row
        for col, header in enumerate(detail_headers, 1):
            cell = ws.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        for record in records:
            ws.cell(row, 1, record.id)  # ✅ ID del registro para referencia
            # Convertir fechas a zona horaria de Chile antes de formatear
            if record.date_time_medition:
                medition_date_chile = record.date_time_medition.astimezone(chile_tz)
                ws.cell(row, 2, medition_date_chile.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                ws.cell(row, 2, 'Sin registros')
            # Mejorar formato de Fecha Logger
            if record.date_time_last_logger:
                logger_date_chile = record.date_time_last_logger.astimezone(chile_tz)
                logger_date = logger_date_chile.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger_date = 'Sin registros'
            ws.cell(row, 3, logger_date)
            ws.cell(row, 4, int(float(record.total)) if record.total else 0)  # Total siempre en entero
            ws.cell(row, 5, float(record.flow) if record.flow else 0)
            ws.cell(row, 6, float(record.nivel) if record.nivel else 0)
            ws.cell(row, 7, int(float(record.total_diff)) if record.total_diff else 0)  # Consumo por hora en entero
            ws.cell(row, 8, int(record.pulses) if record.pulses else 0)
            # ✅ Agregar n_voucher: mostrar "-" si está vacío o es None
            voucher_value = record.n_voucher if record.n_voucher else '-'
            ws.cell(row, 9, voucher_value)
            
            for col in range(1, 10):
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


def generate_excel_by_point(point: CatchmentPoint, year: Optional[int] = None, month: Optional[int] = None) -> BytesIO:
    """
    Generar Excel de análisis de telemetría por punto.
    Cada mes tiene su propia pestaña con indicadores y detalle.
    
    ⚠️ OPTIMIZACIONES CRÍTICAS PARA EVITAR TIMEOUT:
    1. Detalle del mes limitado a 2000 registros máximo (muestreo representativo)
    2. Para CAUDAL_PROMEDIO: calcular dinámicamente pero optimizado (cargar registros anteriores de una vez)
    3. Para CAUDAL instantáneo: usar flow guardado en BD
    4. Para indicadores: calcular caudal dinámicamente solo para 50 registros muestreados
    5. Usar agregaciones de BD (Min, Max, Avg) en lugar de procesar todos los registros
    
    RAZÓN DEL TIMEOUT ANTERIOR:
    - average_flow() hace 2 consultas a la BD por cada llamada (busca registro anterior)
    - Con 2000 registros × 2 consultas = 4000 consultas adicionales = TIMEOUT
    
    SOLUCIÓN OPTIMIZADA:
    - Cargar todos los registros del mes de una vez (1 query) y crear cache en memoria
    - Buscar registro anterior en cache (O(1)) en lugar de consultas a BD
    - Reducción: de 4000 consultas a 1 consulta + búsquedas en memoria
    
    Args:
        point: Punto de captación
        year: Año a filtrar (opcional, si no se especifica usa el año actual completo)
        month: Mes a filtrar (opcional, 1-12, si no se especifica procesa todos los meses del año)
    
    Returns:
        BytesIO con el archivo Excel
    """
    wb = Workbook()
    wb.remove(wb.active)
    
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    
    # ✅ Si se especifica año y mes, filtrar solo ese mes
    if year and month:
        year_start = datetime(year, month, 1, tzinfo=chile_tz)
        # Calcular último día del mes
        if month == 12:
            year_end = datetime(year + 1, 1, 1, tzinfo=chile_tz) - timedelta(days=1)
        else:
            year_end = datetime(year, month + 1, 1, tzinfo=chile_tz) - timedelta(days=1)
        year_end = year_end.replace(hour=23, minute=59, second=59)
    elif year:
        # Si solo se especifica año, procesar todo el año
        year_start = datetime(year, 1, 1, tzinfo=chile_tz)
        year_end = datetime(year, 12, 31, 23, 59, 59, tzinfo=chile_tz)
    else:
        # Si no se especifica nada, usar año actual completo
        year_start = datetime(now.year, 1, 1, tzinfo=chile_tz)
        year_end = datetime(now.year, 12, 31, 23, 59, 59, tzinfo=chile_tz)
    
    # ✅ OPTIMIZACIÓN: Verificar si hay datos sin cargar todos los registros
    if not InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=year_start,
        date_time_medition__lte=year_end
    ).exists():
        ws = wb.create_sheet(title="Sin Datos")
        ws['A1'] = "No hay datos para este punto en el período seleccionado"
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer
    
    # ✅ OPTIMIZACIÓN: Obtener meses disponibles usando agregación de BD (más rápido)
    months_data = get_months_with_data(point, year_start, year_end)
    
    # Obtener variables del punto
    vars_info = get_point_variables(point)
    has_totalizado = vars_info['has_totalizado']
    has_caudal_promedio = vars_info['has_caudal_promedio']
    pulses_factor = vars_info['pulses_factor']
    
    # Crear hoja de resumen anual
    ws_summary = wb.create_sheet(title="Resumen Anual", index=0)
    ws_summary['A1'] = f"Resumen Anual - {point.title} ({now.year})"
    ws_summary['A1'].font = TITLE_FONT
    ws_summary.merge_cells('A1:D1')
    
    # Información del Pozo y DGA
    profile = point.data_config_profiles.first()
    dga_config = point.dga_data_config_profiles.first()
    row = 3
    
    # Usar funciones del módulo excel_writers
    row = write_pozo_info(ws_summary, profile, point, row)  # ✅ Pasar point para tipo de caudal
    row = write_dga_info(ws_summary, dga_config, point, row)
    
    # Últimos 5 registros enviados a DGA (con voucher)
    dga_records = InteractionDetail.objects.filter(
        catchment_point=point,
        n_voucher__isnull=False
    ).exclude(
        n_voucher=''
    ).order_by('-date_time_medition')[:5]
    
    if dga_records.exists():
        ws_summary[f'A{row}'] = "Últimos 5 Registros Enviados a DGA"
        ws_summary[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        # Determinar nombre de columna de caudal según tipo
        caudal_header = "Caudal Promedio (L/s)" if has_caudal_promedio else "Caudal (L/s)"
        dga_headers = ['ID', 'Fecha Medición', 'Fecha Logger', 'Totalizado (m³)', caudal_header, 'Nivel (m)', 'Nivel Freático (m)']
        dga_table_start_row = row  # Guardar fila de inicio de la tabla DGA
        for col, header in enumerate(dga_headers, 1):
            cell = ws_summary.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        row += 1
        
        # Convertir a lista para poder acceder a registros anteriores
        dga_records_list = list(dga_records)
        
        for idx, dga_rec in enumerate(dga_records_list):
            ws_summary.cell(row, 1, dga_rec.id)  # ✅ ID del registro para referencia
            # Convertir fechas a zona horaria de Chile antes de formatear
            if dga_rec.date_time_medition:
                medition_date_chile = dga_rec.date_time_medition.astimezone(chile_tz)
                ws_summary.cell(row, 2, medition_date_chile.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                ws_summary.cell(row, 2, 'Sin registros')
            # Mejorar formato de Fecha Logger
            if dga_rec.date_time_last_logger:
                logger_date_chile = dga_rec.date_time_last_logger.astimezone(chile_tz)
                logger_date = logger_date_chile.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger_date = 'Sin registros'
            ws_summary.cell(row, 3, logger_date)
            ws_summary.cell(row, 4, int(float(dga_rec.total)) if dga_rec.total else 0)
            
            # Calcular caudal según tipo de punto
            if has_caudal_promedio:
                # Para CAUDAL_PROMEDIO: calcular usando registro anterior
                if idx < len(dga_records_list) - 1:
                    prev_record = dga_records_list[idx + 1]  # El siguiente en la lista (anterior en tiempo)
                else:
                    # Buscar registro anterior en BD
                    prev_record = InteractionDetail.objects.filter(
                        catchment_point=point,
                        date_time_medition__lt=dga_rec.date_time_medition
                    ).order_by('-date_time_medition').first()
                
                flow_value = calculate_flow_optimized(dga_rec, prev_record, has_caudal_promedio, point.id)
            else:
                # Para CAUDAL instantáneo: usar flow guardado
                flow_value = float(dga_rec.flow) if dga_rec.flow else 0.0
            
            ws_summary.cell(row, 5, flow_value)
            ws_summary.cell(row, 6, float(dga_rec.nivel) if dga_rec.nivel else 0)
            ws_summary.cell(row, 7, float(dga_rec.water_table) if dga_rec.water_table else 0)
            
            for col in range(1, 8):
                ws_summary.cell(row, col).border = BORDER
            row += 1
        
        dga_table_end_row = row - 1  # Guardar fila final de la tabla DGA
        row += 1
    else:
        dga_table_start_row = None
        dga_table_end_row = None
    
    # Indicadores anuales
    row = write_section_title(ws_summary, "Indicadores del Año", row)
    
    # ✅ OPTIMIZACIÓN: Calcular indicadores anuales usando agregaciones de BD
    annual_stats = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=year_start,
        date_time_medition__lte=year_end
    ).aggregate(
        total_registros=Count('id'),
        avg_flow=Avg('flow'),
        max_flow=Max('flow'),
        min_flow=Min('flow'),
        avg_nivel=Avg('nivel'),
        max_nivel=Max('nivel'),
        min_nivel=Min('nivel'),
        sum_total_diff=Sum('total_diff')
    )
    
    # Calcular consumo total del año
    consumo_total_anual = calculate_month_consumo(point, year_start, year_end, has_totalizado)
    
    # Obtener primer registro del año
    primer_registro_anual = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=year_start,
        date_time_medition__lte=year_end
    ).order_by('date_time_medition').first()
    
    # Calcular caudal mínimo (solo valores > 0)
    min_flow = annual_stats.get('min_flow')
    if min_flow and min_flow <= 0:
        min_flow_positive = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=year_start,
            date_time_medition__lte=year_end,
            flow__gt=0
        ).aggregate(min_flow_positive=Min('flow'))
        min_flow = min_flow_positive.get('min_flow_positive') if min_flow_positive.get('min_flow_positive') else 0.0
    
    # Nombre del indicador de caudal según tipo
    nombre_caudal_promedio = "Promedio Caudal (Promedio)" if has_caudal_promedio else "Promedio Caudal"
    
    annual_indicators = [
        ['Total registros', format_number_with_thousands(annual_stats.get('total_registros', 0))],
    ]
    
    # ✅ Agregar primer registro del año con fecha y primer totalizado
    if primer_registro_anual:
        fecha_primer = primer_registro_anual.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if primer_registro_anual.date_time_medition else 'Sin registros'
        primer_total = format_number_with_thousands(int(float(primer_registro_anual.total))) if primer_registro_anual.total else 'Sin registros'
        annual_indicators.append(['Primer registro del año', f"{fecha_primer} - Total: {primer_total} m³"])
    
    annual_indicators.extend([
        ['Consumo total año', format_decimal(consumo_total_anual, 2) + ' m³'],
        [nombre_caudal_promedio, format_decimal(annual_stats.get('avg_flow'), 2) + ' L/s' if annual_stats.get('avg_flow') else "0.00 L/s"],  # ✅ Nombre según tipo
        ['Caudal máximo año', format_decimal(annual_stats.get('max_flow'), 2) + ' L/s' if annual_stats.get('max_flow') else "0.00 L/s"],
        ['Caudal mínimo año', format_decimal(min_flow, 2) + ' L/s' if min_flow and min_flow > 0 else "0.00 L/s"],
        ['Nivel promedio año', format_decimal(annual_stats.get('avg_nivel'), 2) + ' m' if annual_stats.get('avg_nivel') else "0.00 m"],
        ['Nivel máximo año', format_decimal(annual_stats.get('max_nivel'), 2) + ' m' if annual_stats.get('max_nivel') else "0.00 m"],
        ['Nivel mínimo año', format_decimal(annual_stats.get('min_nivel'), 2) + ' m' if annual_stats.get('min_nivel') else "0.00 m"],
    ])
    
    row = write_indicators_table(ws_summary, annual_indicators, row)
    
    # Ajustar ancho de columnas automáticamente
    # Columnas A y B (información básica)
    ws_summary.column_dimensions['A'].width = 25
    ws_summary.column_dimensions['B'].width = 20
    
    # Ajustar ancho de columnas para tabla DGA si existe
    if dga_table_start_row is not None:
        for col_idx in range(1, 8):  # Columnas 1-7 (ID, Fecha Medición, Fecha Logger, Totalizado, Caudal, Nivel, Nivel Freático)
            col_letter = get_column_letter(col_idx)
            max_length = len(dga_headers[col_idx - 1])  # Longitud del header
            
            # Calcular ancho basado en los datos
            for row_idx in range(dga_table_start_row, dga_table_end_row + 1):
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
        month_info = months_data[month_key]
        month_num = month_key.split('-')[1]
        month_name = month_names.get(month_num, month_key)
        ws = wb.create_sheet(title=f"{month_name} {month_key.split('-')[0]}")
        
        # Título
        ws['A1'] = f"{point.title} - {month_name} {month_key.split('-')[0]}"
        ws['A1'].font = TITLE_FONT
        ws.merge_cells('A1:G1')
        
        row = 3
        
        # ✅ OPTIMIZACIÓN: Cargar registros del mes solo cuando se necesiten
        # Calcular fechas de inicio y fin del mes
        month_start = month_info['start']
        month_end = month_info['end']
        
        # ✅ OPTIMIZACIÓN: Obtener estadísticas usando agregaciones de BD
        month_stats = get_month_statistics(point, month_start, month_end)
        
        # ✅ Calcular consumo total del mes
        consumo_total_mes = calculate_month_consumo(point, month_start, month_end, has_totalizado)
        
        # ✅ OPTIMIZACIÓN CRÍTICA: Calcular caudales solo para una muestra pequeña (máximo 50 registros)
        month_flows = get_month_flows_sample(point, month_start, month_end, has_caudal_promedio, sample_size=50)
        
        # Indicadores del mes
        row = write_section_title(ws, f"Indicadores del Mes - {month_name}", row)
        
        month_indicators = [
            ['Total registros', format_number_with_thousands(month_stats.get('total_registros', 0))],
            ['Consumo total mes', format_decimal(consumo_total_mes, 2) + ' m³'],
            ['Caudal promedio mes', format_decimal(sum(month_flows) / len(month_flows), 2) + ' L/s' if month_flows else "0.00 L/s"],
            ['Caudal máximo mes', format_decimal(max(month_flows), 2) + ' L/s' if month_flows else "0.00 L/s"],
            ['Caudal mínimo mes', format_decimal(min([f for f in month_flows if f > 0]), 2) + ' L/s' if any(f > 0 for f in month_flows) else "0.00 L/s"],
            ['Nivel promedio mes', format_decimal(month_stats.get('avg_nivel'), 2) + ' m' if month_stats.get('avg_nivel') else "0.00 m"],
            ['Nivel máximo mes', format_decimal(month_stats.get('max_nivel'), 2) + ' m' if month_stats.get('max_nivel') else "0.00 m"],
            ['Nivel mínimo mes', format_decimal(month_stats.get('min_nivel'), 2) + ' m' if month_stats.get('min_nivel') else "0.00 m"],
        ]
        
        row = write_indicators_table(ws, month_indicators, row)
        row += 1
        
        # ✅ OPTIMIZACIÓN: Obtener registros DGA directamente de BD
        month_dga_records = list(InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=month_start,
            date_time_medition__lte=month_end,
            send_dga=True
        ).order_by('-date_time_medition')[:5])
        
        if month_dga_records:
            row = write_dga_records_table(ws, month_dga_records, month_name, row)
            row += 1
        
        # Detalle del mes
        row = write_section_title(ws, f"Detalle del Mes - {month_name}", row)
        
        # ✅ Reordenar columnas: ID, Fecha Medición, Fecha Logger, Totalizado, Consumo m³, Caudal/Caudal Promedio, Nivel, Nivel Freático, Voucher DGA
        caudal_header = "Caudal Promedio (L/s)" if has_caudal_promedio else "Caudal (L/s)"
        detail_headers = ['ID', 'Fecha Medición', 'Fecha Logger', 'Totalizado (m³)', 'Consumo (m³)', caudal_header, 'Nivel (m)', 'Nivel Freático (m)', 'Voucher DGA']
        detail_start_row = row  # Guardar fila donde empieza el detalle para los gráficos
        row = create_header_row(ws, detail_headers, row)
        
        # ✅ OPTIMIZACIÓN CRÍTICA: Limitar el detalle del mes a máximo 744 registros (uno por hora)
        # Filtra solo registros con hora exacta (:00:00) en date_time_medition
        month_records, total_records_month = get_month_records_optimized(
            point, month_start, month_end, max_records=744
        )
        
        if total_records_month > len(month_records):
            ws.cell(row, 1, f"⚠️ Nota: Se muestran {len(month_records)} registros (uno por hora) de {total_records_month} totales del mes")
            ws.cell(row, 1).font = Font(italic=True, color="FF6600")
            row += 1
        
        # ✅ OPTIMIZACIÓN CRÍTICA: Calcular flow de forma eficiente evitando N+1 queries
        # Si es CAUDAL_PROMEDIO: calcular dinámicamente pero optimizado
        # Si es CAUDAL instantáneo: usar flow guardado en BD
        # ESTRATEGIA: Cargar registros anteriores ordenados y mantener registro previo en memoria
        
        # Cargar registros anteriores ordenados para cálculo optimizado de CAUDAL_PROMEDIO
        # Solo si el punto tiene CAUDAL_PROMEDIO (evita carga innecesaria)
        prev_record_cache = None
        if has_caudal_promedio and month_records:
            # Cargar solo los registros anteriores al primer registro del detalle
            # Esto es mucho más eficiente que cargar todos los registros del mes
            first_record_ts = month_records[0].date_time_medition
            # Cargar el registro anterior más cercano (solo 1 query)
            prev_record_cache = InteractionDetail.objects.filter(
                catchment_point=point,
                date_time_medition__lt=first_record_ts
            ).order_by('-date_time_medition').only('id', 'date_time_medition', 'date_time_last_logger', 'total').first()
        
        # Obtener caudal autorizado DGA para pintar en rojo
        caudal_autorizado_dga = None
        if dga_config and dga_config.send_dga and dga_config.flow_granted_dga:
            caudal_autorizado_dga = float(dga_config.flow_granted_dga)
        
        for idx, record in enumerate(month_records):
            # ✅ Reordenar: ID, Fecha Medición, Fecha Logger, Totalizado, Consumo m³, Caudal, Nivel, Nivel Freático, Voucher DGA
            ws.cell(row, 1, record.id)  # ID
            
            # Convertir fechas a zona horaria de Chile antes de formatear
            if record.date_time_medition:
                medition_date_chile = record.date_time_medition.astimezone(chile_tz)
                ws.cell(row, 2, medition_date_chile.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                ws.cell(row, 2, 'Sin registros')
            
            # Fecha Logger
            if record.date_time_last_logger:
                logger_date_chile = record.date_time_last_logger.astimezone(chile_tz)
                logger_date = logger_date_chile.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger_date = 'Sin registros'
            ws.cell(row, 3, logger_date)  # Fecha Logger
            
            ws.cell(row, 4, int(float(record.total)) if record.total else 0)  # Totalizado (m³)
            
            # Consumo m³ (total_diff acumulado, no por hora)
            consumo_m3 = float(record.total_diff) if record.total_diff else 0.0
            ws.cell(row, 5, consumo_m3)  # Consumo (m³)
            
            # ✅ CALCULAR FLOW DE FORMA OPTIMIZADA
            flow_value = calculate_flow_optimized(
                record,
                prev_record_cache if idx == 0 else month_records[idx - 1],
                has_caudal_promedio,
                point.id
            )
            
            # Actualizar cache para el siguiente registro
            if has_caudal_promedio:
                prev_record_cache = record
            
            # ✅ Pintar en rojo si supera el autorizado DGA
            flow_cell = ws.cell(row, 6, flow_value)  # Caudal
            if caudal_autorizado_dga and flow_value > caudal_autorizado_dga:
                flow_cell.font = Font(color="FF0000", bold=True)  # Rojo y negrita
            
            ws.cell(row, 7, float(record.nivel) if record.nivel else 0)  # Nivel (m)
            ws.cell(row, 8, float(record.water_table) if record.water_table else 0)  # Nivel Freático (m)
            
            # Voucher DGA
            voucher_value = record.n_voucher if record.n_voucher else '-'
            ws.cell(row, 9, voucher_value)  # Voucher DGA
            
            # Aplicar bordes a todas las columnas
            for col in range(1, 10):
                ws.cell(row, col).border = BORDER
            row += 1
        
        detail_end_row = row - 1
        
        # Ajustar ancho de columnas automáticamente
        auto_adjust_column_width(ws, detail_headers, detail_start_row, detail_end_row)
        
        # ✅ Agregar gráficos del mes usando el módulo excel_charts
        add_month_charts(
            ws, month_name, month_records,
            detail_start_row, detail_end_row,
            has_caudal_promedio, has_totalizado,
            len(detail_headers)
        )
    
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
    
    # Calcular último mes COMPLETO (siempre el mes anterior)
    # Si estamos en enero 2026, el último mes completo es diciembre 2025
    current_month = now.month
    current_year = now.year
    
    # Siempre usar el mes anterior como "último mes completo"
    if current_month == 1:
        last_month = 12
        last_month_year = current_year - 1
    else:
        last_month = current_month - 1
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
    
    # ========================================
    # NUEVOS HEADERS MEJORADOS
    # ========================================
    summary_headers = [
        'Punto', 'Código Obra', 'Standard',  # Info estática
        'Total Mediciones', 'Consumo Mensual (m³)',  # Métricas mensuales
        'Caudal Prom (L/s)', 'Caudal Máx (L/s)', 'Caudal Mín (L/s)',  # Caudal mensual
        'Nivel Prom (m)', 'Nivel Máx (m)', 'Nivel Mín (m)',  # Nivel mensual
        'Total Actual (m³)',  # Totalizado actual
        'Consumo Anual (m³)',  # Métricas anuales
        'Caudal Máx Anual', 'Caudal Mín Anual',  # Caudal anual
        'Nivel F Máx Anual', 'Nivel F Mín Anual'  # Nivel freático anual
    ]
    for col, header in enumerate(summary_headers, 1):
        cell = ws_summary.cell(row, col, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = BORDER
    row += 1
    
    # Análisis combinado
    all_analysis = []
    dga_warnings = []
    
    # Calcular el año correspondiente a las mediciones
    report_year = last_month_year
    year_start_annual = datetime(report_year, 1, 1, tzinfo=chile_tz)
    year_end_annual = datetime(report_year, 12, 31, 23, 59, 59, tzinfo=chile_tz)
    
    for point in points:
        # Obtener configuración DGA para código de obra y standard
        dga_config = point.dga_data_config_profiles.first()
        codigo_obra = dga_config.code_dga if dga_config and dga_config.code_dga else '-'
        standard = '-'
        if dga_config and dga_config.standard:
            try:
                standard = dga_config.get_standard_display()
            except:
                standard = dga_config.standard or '-'
        
        # Obtener registros del mes
        month_records = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=month_start,
            date_time_medition__lte=month_end
        ).order_by('date_time_medition')
        
        if not month_records.exists():
            ws_summary.cell(row, 1, point.title)
            ws_summary.cell(row, 2, codigo_obra)
            ws_summary.cell(row, 3, standard)
            ws_summary.cell(row, 4, 'Sin datos')
            for col in range(1, len(summary_headers) + 1):
                ws_summary.cell(row, col).border = BORDER
            row += 1
            continue
        
        # Análisis del punto
        analisis = analyze_data_coherence(point.id, days_back=30)
        all_analysis.append(analisis)
        
        # ========================================
        # CALCULAR INDICADORES MENSUALES
        # ========================================
        month_flows = [float(r.flow) if r.flow else 0 for r in month_records if r.flow]
        month_flows_positive = [f for f in month_flows if f > 0]
        month_niveles = [float(r.nivel) if r.nivel else 0 for r in month_records if r.nivel]
        month_niveles_positive = [n for n in month_niveles if n > 0]
        month_consumos = [float(r.total_diff) if r.total_diff else 0 for r in month_records if r.total_diff]
        
        # Total actual
        last_record = month_records.order_by('-date_time_medition').first()
        total_actual = int(float(last_record.total)) if last_record and last_record.total else 0
        
        # ========================================
        # CALCULAR INDICADORES ANUALES
        # ========================================
        annual_stats = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=year_start_annual,
            date_time_medition__lte=year_end_annual
        ).aggregate(
            sum_consumo=Sum('total_diff'),
            max_flow=Max('flow'),
            min_flow=Min('flow'),
            max_water_table=Max('water_table'),
            min_water_table=Min('water_table')
        )
        
        consumo_anual = annual_stats.get('sum_consumo') or 0
        caudal_max_anual = annual_stats.get('max_flow') or 0
        caudal_min_anual = annual_stats.get('min_flow') or 0
        # Obtener mínimo positivo para caudal anual
        if caudal_min_anual <= 0:
            min_flow_positive = InteractionDetail.objects.filter(
                catchment_point=point,
                date_time_medition__gte=year_start_annual,
                date_time_medition__lte=year_end_annual,
                flow__gt=0
            ).aggregate(min_flow=Min('flow'))
            caudal_min_anual = min_flow_positive.get('min_flow') or 0
        nivel_f_max_anual = annual_stats.get('max_water_table') or 0
        nivel_f_min_anual = annual_stats.get('min_water_table') or 0
        
        # Verificar límites DGA
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
        
        # ========================================
        # ESCRIBIR DATOS EN RESUMEN
        # ========================================
        col = 1
        ws_summary.cell(row, col, point.title); col += 1  # Punto
        ws_summary.cell(row, col, codigo_obra); col += 1  # Código Obra
        ws_summary.cell(row, col, standard); col += 1  # Standard
        ws_summary.cell(row, col, len(month_records)); col += 1  # Total Mediciones
        ws_summary.cell(row, col, f"{sum(month_consumos):.2f}"); col += 1  # Consumo Mensual
        ws_summary.cell(row, col, f"{sum(month_flows) / len(month_flows):.2f}" if month_flows else "0.00"); col += 1  # Caudal Prom
        ws_summary.cell(row, col, f"{max(month_flows):.2f}" if month_flows else "0.00"); col += 1  # Caudal Máx
        ws_summary.cell(row, col, f"{min(month_flows_positive):.2f}" if month_flows_positive else "0.00"); col += 1  # Caudal Mín
        ws_summary.cell(row, col, f"{sum(month_niveles) / len(month_niveles):.2f}" if month_niveles else "0.00"); col += 1  # Nivel Prom
        ws_summary.cell(row, col, f"{max(month_niveles):.2f}" if month_niveles else "0.00"); col += 1  # Nivel Máx
        ws_summary.cell(row, col, f"{min(month_niveles_positive):.2f}" if month_niveles_positive else "0.00"); col += 1  # Nivel Mín
        ws_summary.cell(row, col, total_actual); col += 1  # Total Actual
        ws_summary.cell(row, col, f"{consumo_anual:.2f}" if consumo_anual else "0.00"); col += 1  # Consumo Anual
        ws_summary.cell(row, col, f"{float(caudal_max_anual):.2f}" if caudal_max_anual else "0.00"); col += 1  # Caudal Máx Anual
        ws_summary.cell(row, col, f"{float(caudal_min_anual):.2f}" if caudal_min_anual else "0.00"); col += 1  # Caudal Mín Anual
        ws_summary.cell(row, col, f"{float(nivel_f_max_anual):.2f}" if nivel_f_max_anual else "0.00"); col += 1  # Nivel F Máx Anual
        ws_summary.cell(row, col, f"{float(nivel_f_min_anual):.2f}" if nivel_f_min_anual else "0.00"); col += 1  # Nivel F Mín Anual
        
        for c in range(1, len(summary_headers) + 1):
            ws_summary.cell(row, c).border = BORDER
        row += 1
    
    # Ajustar ancho de columnas del resumen automáticamente
    for col in range(1, len(summary_headers) + 1):
        col_letter = get_column_letter(col)
        header_length = len(summary_headers[col - 1])
        max_length = header_length
        
        # Calcular ancho basado en los datos
        for row_idx in range(3, row):
            cell = ws_summary.cell(row_idx, col)
            if cell.value:
                cell_length = len(str(cell.value))
                if cell_length > max_length:
                    max_length = cell_length
        
        # Ajustar ancho con padding (mínimo 10, máximo 25)
        ws_summary.column_dimensions[col_letter].width = min(max(max_length + 2, 10), 25)
    
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
        
        # Información del Pozo y DGA
        profile = point.data_config_profiles.first()
        dga_config = point.dga_data_config_profiles.first()
        
        # Usar funciones del módulo excel_writers
        row = write_pozo_info(ws, profile, point, row)  # ✅ Pasar point para tipo de caudal
        row = write_dga_info(ws, dga_config, point, row)
        
        # Indicadores del mes
        ws[f'A{row}'] = "Indicadores del Mes"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        # Obtener variables del punto
        vars_info = get_point_variables(point)
        has_totalizado = vars_info['has_totalizado']
        has_caudal_promedio = vars_info['has_caudal_promedio']
        
        # ✅ OPTIMIZACIÓN: Obtener estadísticas usando agregaciones de BD
        month_stats = get_month_statistics(point, month_start, month_end)
        
        # ✅ Calcular consumo total del mes
        consumo_total_mes = calculate_month_consumo(point, month_start, month_end, has_totalizado)
        
        # ✅ OPTIMIZACIÓN CRÍTICA: Calcular caudales solo para una muestra pequeña
        month_flows = get_month_flows_sample(point, month_start, month_end, has_caudal_promedio, sample_size=50)
        
        # Indicadores del mes
        row = write_section_title(ws, f"Indicadores del Mes - {month_name}", row)
        
        # ✅ Calcular veces que el caudal superó el autorizado DGA
        veces_supero_autorizado = 0
        if dga_config and dga_config.send_dga and dga_config.flow_granted_dga:
            caudal_autorizado = float(dga_config.flow_granted_dga)
            veces_supero_autorizado = InteractionDetail.objects.filter(
                catchment_point=point,
                date_time_medition__gte=month_start,
                date_time_medition__lte=month_end,
                flow__gt=caudal_autorizado
            ).count()
        
        # Nombre del indicador de caudal según tipo
        nombre_caudal_promedio = "Promedio Caudal (Promedio)" if has_caudal_promedio else "Promedio Caudal"
        
        month_indicators = [
            ['Total registros', format_number_with_thousands(month_stats.get('total_registros', 0))],  # ✅ Sin "mes"
            ['Consumo total', format_decimal(consumo_total_mes, 2) + ' m³'],  # ✅ Sin "mes"
            [nombre_caudal_promedio, format_decimal(sum(month_flows) / len(month_flows), 2) + ' L/s' if month_flows else "0.00 L/s"],  # ✅ Nombre según tipo
            ['Caudal máximo', format_decimal(max(month_flows), 2) + ' L/s' if month_flows else "0.00 L/s"],  # ✅ Sin "mes"
            ['Caudal mínimo', format_decimal(min([f for f in month_flows if f > 0]), 2) + ' L/s' if any(f > 0 for f in month_flows) else "0.00 L/s"],  # ✅ Sin "mes"
            ['Nivel promedio', format_decimal(month_stats.get('avg_nivel'), 2) + ' m' if month_stats.get('avg_nivel') else "0.00 m"],  # ✅ Sin "mes"
            ['Nivel máximo', format_decimal(month_stats.get('max_nivel'), 2) + ' m' if month_stats.get('max_nivel') else "0.00 m"],  # ✅ Sin "mes"
            ['Nivel mínimo', format_decimal(month_stats.get('min_nivel'), 2) + ' m' if month_stats.get('min_nivel') else "0.00 m"],  # ✅ Sin "mes"
        ]
        
        # ✅ Agregar contador de superaciones DGA solo si tiene DGA configurado
        if dga_config and dga_config.send_dga and dga_config.flow_granted_dga:
            month_indicators.append(['Veces que caudal superó autorizado DGA', str(veces_supero_autorizado)])
        
        if has_totalizado:
            last_record = month_records.order_by('-date_time_medition').first()
            total_actual = int(float(last_record.total)) if last_record and last_record.total else 0
            month_indicators.append(['Total Actual (m³)', format_number_with_thousands(total_actual)])
        
        row = write_indicators_table(ws, month_indicators, row)
        row += 1
        
        # Detalle del mes
        row = write_section_title(ws, f"Detalle del Mes - {month_name}", row)
        
        # ✅ OPTIMIZACIÓN CRÍTICA: Limitar el detalle del mes a máximo 744 registros (uno por hora)
        # Filtra solo registros con hora exacta (:00:00) en date_time_medition
        month_records_list, total_records_month = get_month_records_optimized(
            point, month_start, month_end, max_records=744
        )
        
        if total_records_month > len(month_records_list):
            ws.cell(row, 1, f"⚠️ Nota: Se muestran {len(month_records_list)} registros (uno por hora) de {total_records_month} totales del mes")
            ws.cell(row, 1).font = Font(italic=True, color="FF6600")
            row += 1
        
        # ✅ Reordenar columnas: ID, Fecha Medición, Fecha Logger, Totalizado, Consumo m³, Caudal/Caudal Promedio, Nivel, Nivel Freático, Voucher DGA
        caudal_header = "Caudal Promedio (L/s)" if has_caudal_promedio else "Caudal (L/s)"
        detail_headers = ['ID', 'Fecha Medición', 'Fecha Logger', 'Totalizado (m³)', 'Consumo (m³)', caudal_header, 'Nivel (m)', 'Nivel Freático (m)', 'Voucher DGA']
        detail_start_row = row
        row = create_header_row(ws, detail_headers, row)
        
        # Obtener caudal autorizado DGA para pintar en rojo
        caudal_autorizado_dga = None
        if dga_config and dga_config.send_dga and dga_config.flow_granted_dga:
            caudal_autorizado_dga = float(dga_config.flow_granted_dga)
        
        # ✅ OPTIMIZACIÓN: Calcular flow de forma eficiente
        prev_record_cache = None
        if has_caudal_promedio and month_records_list:
            first_record_ts = month_records_list[0].date_time_medition
            prev_record_cache = InteractionDetail.objects.filter(
                catchment_point=point,
                date_time_medition__lt=first_record_ts
            ).order_by('-date_time_medition').only('id', 'date_time_medition', 'date_time_last_logger', 'total').first()
        
        for idx, record in enumerate(month_records_list):
            # Convertir fechas a zona horaria de Chile
            if record.date_time_last_logger:
                logger_date_chile = record.date_time_last_logger.astimezone(chile_tz)
                logger_date = logger_date_chile.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger_date = 'Sin registros'
            voucher_value = record.n_voucher if record.n_voucher else '-'
            
            # ✅ CALCULAR FLOW DE FORMA OPTIMIZADA
            flow_value = calculate_flow_optimized(
                record,
                prev_record_cache if idx == 0 else month_records_list[idx - 1],
                has_caudal_promedio,
                point.id
            )
            
            if has_caudal_promedio:
                prev_record_cache = record
            
            # ✅ Reordenar: ID, Fecha Medición, Fecha Logger, Totalizado, Consumo m³, Caudal, Nivel, Nivel Freático, Voucher DGA
            ws.cell(row, 1, record.id)  # ID
            # Convertir fecha de medición a Chile
            if record.date_time_medition:
                medition_date_chile = record.date_time_medition.astimezone(chile_tz)
                ws.cell(row, 2, medition_date_chile.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                ws.cell(row, 2, 'Sin registros')
            ws.cell(row, 3, logger_date)  # Fecha Logger
            ws.cell(row, 4, int(float(record.total)) if record.total else 0)  # Totalizado (m³)
            ws.cell(row, 5, float(record.total_diff) if record.total_diff else 0.0)  # Consumo (m³)
            
            # ✅ Pintar en rojo si supera el autorizado DGA
            flow_cell = ws.cell(row, 6, flow_value)  # Caudal
            if caudal_autorizado_dga and flow_value > caudal_autorizado_dga:
                flow_cell.font = Font(color="FF0000", bold=True)  # Rojo y negrita
            
            ws.cell(row, 7, float(record.nivel) if record.nivel else 0)  # Nivel (m)
            ws.cell(row, 8, float(record.water_table) if record.water_table else 0)  # Nivel Freático (m)
            ws.cell(row, 9, voucher_value)  # Voucher DGA
            
            # Aplicar bordes a todas las columnas
            for col in range(1, 10):
                ws.cell(row, col).border = BORDER
            row += 1
        
        detail_end_row = row - 1
        
        # Ajustar ancho de columnas automáticamente
        auto_adjust_column_width(ws, detail_headers, detail_start_row, detail_end_row)
        
        # ✅ Agregar gráficos del mes usando el módulo excel_charts
        add_month_charts(
            ws, month_name, month_records_list,
            detail_start_row, detail_end_row,
            has_caudal_promedio, has_totalizado,
            len(detail_headers)
        )
    
    # Guardar en buffer
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def generate_excel_last_year_by_points(points: List[CatchmentPoint], project_name: Optional[str] = None) -> BytesIO:
    """
    Generar Excel del AÑO ANTERIOR completo para varios puntos.
    Cada punto tiene su propia pestaña y hay un resumen combinado.
    
    Args:
        points: Lista de puntos de captación
        project_name: Nombre del proyecto (opcional)
    
    Returns:
        BytesIO con el archivo Excel
    """
    from api.core.models import DgaDataConfigCatchment
    
    wb = Workbook()
    wb.remove(wb.active)
    
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    
    # Calcular último año completo (año anterior)
    prev_year = now.year - 1
    year_start = datetime(prev_year, 1, 1, tzinfo=chile_tz)
    year_end = datetime(prev_year, 12, 31, 23, 59, 59, tzinfo=chile_tz)
    
    # ========================================
    # HOJA DE RESUMEN COMBINADO
    # ========================================
    ws_summary = wb.create_sheet(title="Resumen Anual", index=0)
    ws_summary['A1'] = f"Resumen Anual - Año {prev_year}"
    if project_name:
        ws_summary['A1'] = f"Resumen Anual - Año {prev_year} - {project_name}"
    ws_summary['A1'].font = TITLE_FONT
    ws_summary.merge_cells('A1:F1')
    
    row = 3
    ws_summary[f'A{row}'] = f"Período: {year_start.strftime('%Y-%m-%d')} a {year_end.strftime('%Y-%m-%d')}"
    ws_summary[f'A{row}'].font = Font(bold=True, size=11)
    row += 1
    
    # Tabla resumen combinada de todos los puntos
    ws_summary[f'A{row}'] = "Resumen de Puntos de Captación"
    ws_summary[f'A{row}'].font = Font(bold=True, size=12)
    row += 1
    
    summary_headers = ['Punto', 'Total Mediciones', 'Consumo Total (m³)', 'Caudal Promedio (L/s)', 
                      'Caudal Máximo (L/s)', 'Nivel Promedio (m)', 'Total Fin Año (m³)']
    for col, header in enumerate(summary_headers, 1):
        cell = ws_summary.cell(row, col, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = BORDER
    row += 1
    
    # Análisis combinado
    all_analysis = []
    
    for point in points:
        # Optimización: Consultar agregaciones directamente para el resumen
        annual_stats = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=year_start,
            date_time_medition__lte=year_end
        ).aggregate(
            total_count=Count('id'),
            sum_diff=Sum('total_diff'),
            max_flow=Max('flow'),
            avg_flow=Avg('flow'),
            avg_level=Avg('nivel'),
            max_total=Max('total')
        )
        
        ws_summary.cell(row, 1, point.title).border = BORDER
        ws_summary.cell(row, 2, annual_stats['total_count'] or 0).border = BORDER
        ws_summary.cell(row, 3, float(annual_stats['sum_diff'] or 0)).border = BORDER
        ws_summary.cell(row, 4, float(annual_stats['avg_flow'] or 0)).border = BORDER
        ws_summary.cell(row, 5, float(annual_stats['max_flow'] or 0)).border = BORDER
        ws_summary.cell(row, 6, float(annual_stats['avg_level'] or 0)).border = BORDER
        ws_summary.cell(row, 7, int(float(annual_stats['max_total'] or 0)) if annual_stats['max_total'] else 0).border = BORDER
        row += 1
        
        all_analysis.append({
            'point': point,
            'stats': annual_stats
        })
            
    # Ajustar ancho de columnas resumen
    for col in range(1, 8):
        ws_summary.column_dimensions[get_column_letter(col)].width = 20
    ws_summary.column_dimensions['A'].width = 40
    
    
    # ========================================
    # PESTAÑAS INDIVIDUALES POR PUNTO
    # ========================================
    
    for analysis in all_analysis:
        point = analysis['point']
        
        # Limpiar caracteres inválidos para nombre de hoja de Excel
        safe_title = "".join([c for c in point.title if c.isalnum() or c in (' ','-','_')])[:30]
        ws = wb.create_sheet(title=safe_title)
        
        # Encabezado Puntual
        ws['A1'] = f"Reporte Anual {prev_year} - {point.title}"
        ws['A1'].font = TITLE_FONT
        ws.merge_cells('A1:H1')
        
        row = 3
        dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
        caudal_autorizado_dga = float(dga_config.flow_granted_dga) if dga_config and dga_config.flow_granted_dga else None
        
        # Encabezados de detalle
        detail_headers = ['Fecha/Hora', 'Fecha/Hora Chile', 'Fecha Logger', 'Totalizado (m³)', 'Consumo (m³)', 'Caudal (L/s)', 'Nivel (m)', 'N. Freático (m)', 'Voucher DGA']
        for col, header in enumerate(detail_headers, 1):
            cell = ws.cell(row, col, header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
        
        detail_start_row = row + 1
        row += 1
        
        # Obtener registros (Iterador para memoria eficiente)
        year_records_iter = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=year_start,
            date_time_medition__lte=year_end
        ).order_by('date_time_medition').iterator(chunk_size=2000)
        
        for record in year_records_iter:
            flow_value = float(record.flow) if record.flow else 0.0
            voucher_value = record.return_dga if record.return_dga else '-'
            # Manejo robusto de Fecha Logger
            if record.date_time_last_logger:
                if record.date_time_last_logger.tzinfo is None:
                    logger_date_utc = pytz.utc.localize(record.date_time_last_logger)
                    logger_date_chile = logger_date_utc.astimezone(chile_tz)
                else:
                    logger_date_chile = record.date_time_last_logger.astimezone(chile_tz)
                logger_date = logger_date_chile.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger_date = '-'
            
            # Fecha UTC
            ws.cell(row, 1, record.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if record.date_time_medition else '-')
            
            # Fecha Chile
            if record.date_time_medition:
                if record.date_time_medition.tzinfo is None:
                    medition_date_utc = pytz.utc.localize(record.date_time_medition)
                    medition_date_chile = medition_date_utc.astimezone(chile_tz)
                else:
                    medition_date_chile = record.date_time_medition.astimezone(chile_tz)
                ws.cell(row, 2, medition_date_chile.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                ws.cell(row, 2, '-')
                
            ws.cell(row, 3, logger_date)
            # Manejo seguro de Total
            try:
                t_val = int(float(record.total)) if record.total is not None else 0
            except:
                t_val = 0
            ws.cell(row, 4, t_val)
            
            # Manejo seguro de Total Diff
            try:
                td_val = float(record.total_diff) if record.total_diff is not None else 0.0
            except:
                td_val = 0.0
            ws.cell(row, 5, td_val)
            
            # Caudal con alerta
            flow_cell = ws.cell(row, 6, flow_value)
            if caudal_autorizado_dga and flow_value > caudal_autorizado_dga:
                flow_cell.font = Font(color="FF0000", bold=True)
            
            # Manejo seguro de Nivel
            try:
                n_val = float(record.nivel) if record.nivel is not None else 0.0
            except:
                n_val = 0.0
            ws.cell(row, 7, n_val)
            
            # Manejo seguro de Water Table
            try:
                wt_val = float(record.water_table) if record.water_table is not None else 0.0
            except:
                wt_val = 0.0
            ws.cell(row, 8, wt_val)
            
            ws.cell(row, 9, voucher_value)
            
            row += 1
            
        # Autosize básico
        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 20
        ws.column_dimensions['C'].width = 20
        ws.column_dimensions['I'].width = 30
    
    # Guardar en buffer
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

def generate_excel_annual_compressed(points: List[CatchmentPoint], project_name: Optional[str] = None) -> BytesIO:
    """
    Generar Excel Anual CORTO (Comprimido) con resumen mensual por punto.
    Una pestaña por punto con tabla de Enero a Diciembre.
    """
    from django.db.models.functions import ExtractMonth
    from django.db.models import Sum, Avg, Max
    from api.core.models import DgaDataConfigCatchment
    
    wb = Workbook()
    wb.remove(wb.active)
    
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    prev_year = now.year - 1
    
    # ---------------------------------------------------------
    # HOJA RESUMEN GENERAL (Todos los puntos)
    # ---------------------------------------------------------
    ws_summary = wb.create_sheet(title="Resumen General", index=0)
    ws_summary['A1'] = f"Reporte Anual Comprimido {prev_year}"
    ws_summary['A1'].font = TITLE_FONT
    ws_summary.merge_cells('A1:E1')
    
    headers = ['Punto', 'Consumo Total Año (m³)', 'Caudal Promedio Año (L/s)', 'Consumo Promedio Mes (m³)']
    row = 3
    for col, h in enumerate(headers, 1):
        c = ws_summary.cell(row, col, h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.border = BORDER
        ws_summary.column_dimensions[get_column_letter(col)].width = 25
    row += 1
    
    # ---------------------------------------------------------
    # PROCESAR CADA PUNTO
    # ---------------------------------------------------------
    month_names = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    
    for point in points:
        # Recuperar datos agregados por mes
        monthly_data = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__year=prev_year
        ).annotate(
            month=ExtractMonth('date_time_medition')
        ).values('month').annotate(
            total_consumption=Sum('total_diff'),
            avg_flow=Avg('flow'),
            max_flow=Max('flow')
        ).order_by('month')
        
        # Mapear datos a diccionario {mes: data}
        data_by_month = {entry['month']: entry for entry in monthly_data}
        
        # Totales anuales para resumen
        total_year_cons = sum(d['total_consumption'] for d in monthly_data if d['total_consumption'])
        avg_year_flow = sum(d['avg_flow'] for d in monthly_data if d['avg_flow']) / len(monthly_data) if monthly_data else 0
        avg_month_cons = total_year_cons / 12  # Simple promedio
        
        # Escribir en Resumen General
        ws_summary.cell(row, 1, point.title).border = BORDER
        ws_summary.cell(row, 2, float(total_year_cons)).border = BORDER
        ws_summary.cell(row, 3, float(avg_year_flow)).border = BORDER
        ws_summary.cell(row, 4, float(avg_month_cons)).border = BORDER
        row += 1
        
        # -----------------------------------------------------
        # PESTAÑA INDIVIDUAL (Comprimida)
        # -----------------------------------------------------
        safe_title = "".join([c for c in point.title if c.isalnum() or c in (' ','-','_')])[:30]
        ws = wb.create_sheet(title=safe_title)
        
        # Info General
        ws['A1'] = f"Reporte Mensual {prev_year} - {point.title}"
        ws['A1'].font = TITLE_FONT
        
        # Obtener DGA info
        dga_conf = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
        flow_granted = dga_conf.flow_granted_dga if dga_conf else 0
        
        ws.cell(3, 1, "Caudal Autorizado DGA (L/s):")
        ws.cell(3, 2, float(flow_granted) if flow_granted else "N/A")
        
        # Tabla Mensual
        tbl_row = 5
        tbl_headers = ['Mes', 'Consumo (m³)', 'Caudal Promedio (L/s)', 'Caudal Máximo (L/s)']
        for col, h in enumerate(tbl_headers, 1):
            c = ws.cell(tbl_row, col, h)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
            c.border = BORDER
            ws.column_dimensions[get_column_letter(col)].width = 20
        tbl_row += 1
        
        # Llenar Enero a Diciembre
        for m in range(1, 13):
            d = data_by_month.get(m, {})
            cons = float(d.get('total_consumption', 0) or 0)
            aflow = float(d.get('avg_flow', 0) or 0)
            mflow = float(d.get('max_flow', 0) or 0)
            
            ws.cell(tbl_row, 1, month_names[m]).border = BORDER
            ws.cell(tbl_row, 2, cons).border = BORDER
            ws.cell(tbl_row, 3, aflow).border = BORDER
            ws.cell(tbl_row, 4, mflow).border = BORDER
            tbl_row += 1
            
        # Total al pie
        ws.cell(tbl_row, 1, "TOTAL AÑO").font = Font(bold=True)
        ws.cell(tbl_row, 2, float(total_year_cons)).font = Font(bold=True)
            
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
