"""
Funciones para crear gráficos en Excel
=======================================

Funciones especializadas para crear y posicionar gráficos en hojas Excel.
"""

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.utils import get_column_letter
from typing import List
from api.core.models import TelemetryRecord


def create_flow_chart(worksheet, month_name: str, flow_col: int, 
                     start_row: int, end_row: int, 
                     chart_start_col: int, chart_start_row: int,
                     max_data_points: int = 744):
    """
    Crear gráfico de caudal.
    
    ⚠️ OPTIMIZACIÓN: Limita el número de puntos de datos para evitar archivos pesados.
    Límite: 744 puntos (registros cada hora: 24 horas/día × 31 días máximo).
    Si hay más de max_data_points registros, se muestrean para mantener el rendimiento.
    
    Args:
        worksheet: Worksheet de openpyxl
        month_name: Nombre del mes
        flow_col: Columna donde están los datos de caudal
        start_row: Fila inicial de datos
        end_row: Fila final de datos
        chart_start_col: Columna donde posicionar el gráfico
        chart_start_row: Fila donde posicionar el gráfico
        max_data_points: Máximo de puntos de datos en el gráfico (default: 744 = 24h × 31 días)
    """
    chart_flow = LineChart()
    chart_flow.title = f"Caudal (L/s) - {month_name}"
    chart_flow.style = 10
    chart_flow.y_axis.title = 'Caudal (L/s)'
    chart_flow.x_axis.title = 'Registros'
    
    # ✅ OPTIMIZACIÓN: Limitar puntos de datos para evitar archivos pesados
    # Si hay más de max_data_points, limitar el rango para mantener el rendimiento
    total_rows = end_row - start_row + 1
    if total_rows > max_data_points:
        # Limitar a max_data_points filas (tomar desde el inicio)
        # Esto reduce significativamente el tamaño del archivo Excel
        chart_max_row = start_row + max_data_points - 1
        data_flow = Reference(worksheet, min_col=flow_col, min_row=start_row, max_row=chart_max_row)
    else:
        data_flow = Reference(worksheet, min_col=flow_col, min_row=start_row, max_row=end_row)
    
    chart_flow.add_data(data_flow, titles_from_data=False)
    chart_flow.series[0].graphicalProperties.line.solidFill = "0066CC"
    
    chart_col_letter = get_column_letter(chart_start_col)
    worksheet.add_chart(chart_flow, f"{chart_col_letter}{chart_start_row}")


def create_nivel_chart(worksheet, month_name: str, nivel_col: int, 
                      start_row: int, end_row: int, 
                      chart_start_col: int, chart_start_row: int,
                      max_data_points: int = 744):
    """
    Crear gráfico de nivel.
    
    ⚠️ OPTIMIZACIÓN: Limita el número de puntos de datos para evitar archivos pesados.
    Límite: 744 puntos (registros cada hora: 24 horas/día × 31 días máximo).
    
    Args:
        worksheet: Worksheet de openpyxl
        month_name: Nombre del mes
        nivel_col: Columna donde están los datos de nivel
        start_row: Fila inicial de datos
        end_row: Fila final de datos
        chart_start_col: Columna donde posicionar el gráfico
        chart_start_row: Fila donde posicionar el gráfico
        max_data_points: Máximo de puntos de datos en el gráfico (default: 744 = 24h × 31 días)
    """
    chart_nivel = LineChart()
    chart_nivel.title = f"Nivel (m) - {month_name}"
    chart_nivel.style = 10
    chart_nivel.y_axis.title = 'Nivel (m)'
    chart_nivel.x_axis.title = 'Registros'
    
    # ✅ OPTIMIZACIÓN: Limitar puntos de datos
    total_rows = end_row - start_row + 1
    if total_rows > max_data_points:
        chart_max_row = start_row + max_data_points - 1
        data_nivel = Reference(worksheet, min_col=nivel_col, min_row=start_row, max_row=chart_max_row)
    else:
        data_nivel = Reference(worksheet, min_col=nivel_col, min_row=start_row, max_row=end_row)
    
    chart_nivel.add_data(data_nivel, titles_from_data=False)
    chart_nivel.series[0].graphicalProperties.line.solidFill = "00CC66"
    
    chart_col_letter = get_column_letter(chart_start_col)
    worksheet.add_chart(chart_nivel, f"{chart_col_letter}{chart_start_row}")


def create_total_chart(worksheet, month_name: str, total_col: int, 
                       start_row: int, end_row: int, 
                       chart_start_col: int, chart_start_row: int,
                       max_data_points: int = 744):
    """
    Crear gráfico de total.
    
    ⚠️ OPTIMIZACIÓN: Limita el número de puntos de datos para evitar archivos pesados.
    Límite: 744 puntos (registros cada hora: 24 horas/día × 31 días máximo).
    
    Args:
        worksheet: Worksheet de openpyxl
        month_name: Nombre del mes
        total_col: Columna donde están los datos de total
        start_row: Fila inicial de datos
        end_row: Fila final de datos
        chart_start_col: Columna donde posicionar el gráfico
        chart_start_row: Fila donde posicionar el gráfico
        max_data_points: Máximo de puntos de datos en el gráfico (default: 744 = 24h × 31 días)
    """
    chart_total = LineChart()
    chart_total.title = f"Total (m³) - {month_name}"
    chart_total.style = 10
    chart_total.y_axis.title = 'Total (m³)'
    chart_total.x_axis.title = 'Registros'
    
    # ✅ OPTIMIZACIÓN: Limitar puntos de datos
    total_rows = end_row - start_row + 1
    if total_rows > max_data_points:
        chart_max_row = start_row + max_data_points - 1
        data_total = Reference(worksheet, min_col=total_col, min_row=start_row, max_row=chart_max_row)
    else:
        data_total = Reference(worksheet, min_col=total_col, min_row=start_row, max_row=end_row)
    
    chart_total.add_data(data_total, titles_from_data=False)
    chart_total.series[0].graphicalProperties.line.solidFill = "FF6600"
    
    chart_col_letter = get_column_letter(chart_start_col)
    worksheet.add_chart(chart_total, f"{chart_col_letter}{chart_start_row}")


def add_month_charts(worksheet, month_name: str, records: List[TelemetryRecord],
                    detail_start_row: int, detail_end_row: int,
                    has_caudal_promedio: bool, has_totalizado: bool,
                    detail_headers_count: int):
    """
    Agregar todos los gráficos del mes (caudal, nivel, total).
    
    Args:
        worksheet: Worksheet de openpyxl
        month_name: Nombre del mes
        records: Lista de registros
        detail_start_row: Fila inicial del detalle
        detail_end_row: Fila final del detalle
        has_caudal_promedio: Si tiene caudal promedio
        has_totalizado: Si tiene totalizado
        detail_headers_count: Número de columnas de encabezados
    """
    if not records or len(records) <= 1:
        return
    
    # ✅ Calcular posición de gráficos (más a la derecha para dejar espacio a las columnas)
    chart_start_col = detail_headers_count + 4  # ✅ Movido más a la derecha (+4 en lugar de +2)
    
    # ✅ Gráficos: columnas actualizadas según nuevo orden (ID=1, Fecha Med=2, Fecha Log=3, Totalizado=4, Consumo=5, Caudal=6, Nivel=7)
    # Gráfico de Caudal (columna 6)
    if has_caudal_promedio or any(r.flow for r in records if r.flow):
        create_flow_chart(
            worksheet, month_name, 6,  # Columna F (Caudal)
            detail_start_row, detail_end_row,
            chart_start_col, detail_start_row
        )
    
    # Gráfico de Nivel (columna 7)
    if any(r.nivel for r in records if r.nivel):
        create_nivel_chart(
            worksheet, month_name, 7,  # Columna G (Nivel)
            detail_start_row, detail_end_row,
            chart_start_col, detail_start_row + 15
        )
    
    # Gráfico de Total (columna 4 - Totalizado)
    if has_totalizado and any(r.total for r in records if r.total):
        create_total_chart(
            worksheet, month_name, 4,  # Columna D (Totalizado)
            detail_start_row, detail_end_row,
            chart_start_col, detail_start_row + 30
        )

