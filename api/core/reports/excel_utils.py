"""
Utilidades comunes para generación de Excel
===========================================

Funciones reutilizables para crear y formatear archivos Excel:
- Estilos comunes
- Formateo de números y fechas
- Creación de hojas y títulos
- Ajuste de columnas
"""

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from typing import Optional

# Utilidades de formateo centralizadas (elimina duplicación)
from api.core.utils.formatters import format_number_with_thousands as _format_number
from api.core.utils.formatters import format_decimal as _format_decimal


# ========================================
# ESTILOS COMUNES
# ========================================

HEADER_FILL = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(bold=True, size=14)
BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)


# ========================================
# FUNCIONES DE FORMATEO
# ========================================

# Wrappers para mantener compatibilidad con comportamiento existente (retorna 'Sin registros' en lugar de '0')

def format_number_with_thousands(value):
    """
    Formatear número con puntos de miles. Retorna 'Sin registros' si None.

    Args:
        value: Valor numérico a formatear

    Returns:
        str: Número formateado con puntos de miles o 'Sin registros'
    """
    if value is None:
        return 'Sin registros'
    result = _format_number(value)
    return result if result != '0' else 'Sin registros'


def format_decimal(value, decimals=2):
    """
    Formatear decimal con puntos de miles. Retorna 'Sin registros' si None.

    Args:
        value: Valor numérico a formatear
        decimals: Número de decimales (default: 2)

    Returns:
        str: Decimal formateado con puntos de miles o 'Sin registros'
    """
    if value is None:
        return 'Sin registros'
    result = _format_decimal(value, decimals)
    # Si es 0, puede ser válido (no siempre es 'Sin registros')
    return result


def calculate_variation_percentage(min_val, max_val):
    """
    Calcular variación como porcentaje.
    
    Args:
        min_val: Valor mínimo
        max_val: Valor máximo
        
    Returns:
        float: Porcentaje de variación o None si no se puede calcular
    """
    if min_val is None or max_val is None or min_val == 0:
        return None
    try:
        return ((max_val - min_val) / min_val) * 100
    except (ZeroDivisionError, TypeError):
        return None


# ========================================
# FUNCIONES DE CREACIÓN DE HOJAS
# ========================================

def create_sheet_with_title(workbook, title: str, subtitle: Optional[str] = None, 
                            merge_range: str = "A1:F1") -> tuple:
    """
    Crear una nueva hoja en el workbook con título formateado.
    
    Args:
        workbook: Workbook de openpyxl
        title: Título principal de la hoja
        subtitle: Subtítulo opcional
        merge_range: Rango de celdas a fusionar para el título
        
    Returns:
        tuple: (worksheet, row) donde row es la siguiente fila disponible
    """
    ws = workbook.create_sheet(title=title[:31])  # Excel limita a 31 caracteres
    ws['A1'] = subtitle if subtitle else title
    ws['A1'].font = TITLE_FONT
    ws.merge_cells(merge_range)
    return ws, 3


def create_header_row(worksheet, headers: list, row: int, 
                     fill=HEADER_FILL, font=HEADER_FONT, border=BORDER) -> int:
    """
    Crear fila de encabezados con estilos aplicados.
    
    Args:
        worksheet: Worksheet de openpyxl
        headers: Lista de textos de encabezados
        row: Fila donde empezar
        fill: Fill pattern para encabezados
        font: Font para encabezados
        border: Border para encabezados
        
    Returns:
        int: Siguiente fila disponible
    """
    for col, header in enumerate(headers, 1):
        cell = worksheet.cell(row, col, header)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border
    return row + 1


# ========================================
# FUNCIONES DE AJUSTE DE COLUMNAS
# ========================================

def auto_adjust_column_width(worksheet, headers: list, start_row: int, 
                            end_row: int, min_width: int = 12, max_width: int = 30):
    """
    Ajustar automáticamente el ancho de columnas según el contenido.
    
    Args:
        worksheet: Worksheet de openpyxl
        headers: Lista de encabezados (para calcular ancho mínimo)
        start_row: Fila inicial donde empiezan los datos
        end_row: Fila final donde terminan los datos
        min_width: Ancho mínimo de columna
        max_width: Ancho máximo de columna
    """
    for col in range(1, len(headers) + 1):
        col_letter = get_column_letter(col)
        header_length = len(headers[col - 1])
        max_length = header_length
        
        # Calcular ancho basado en los datos
        for row_idx in range(start_row, end_row + 1):
            cell = worksheet.cell(row_idx, col)
            if cell.value:
                cell_length = len(str(cell.value))
                if cell_length > max_length:
                    max_length = cell_length
        
        # Ajustar ancho con padding
        worksheet.column_dimensions[col_letter].width = min(max(max_length + 2, min_width), max_width)


# ========================================
# FUNCIONES DE ESCRITURA DE DATOS
# ========================================

def write_data_row(worksheet, data: list, row: int, border=BORDER, 
                  bold_first_col: bool = False) -> int:
    """
    Escribir una fila de datos con bordes aplicados.
    
    Args:
        worksheet: Worksheet de openpyxl
        data: Lista de valores a escribir
        row: Fila donde escribir
        border: Border a aplicar
        bold_first_col: Si True, la primera columna será en negrita
        
    Returns:
        int: Siguiente fila disponible
    """
    for col, value in enumerate(data, 1):
        cell = worksheet.cell(row, col, value)
        cell.border = border
        if bold_first_col and col == 1:
            cell.font = Font(bold=True)
    return row + 1


def write_section_title(worksheet, title: str, row: int, 
                       font_size: int = 12) -> int:
    """
    Escribir título de sección.
    
    Args:
        worksheet: Worksheet de openpyxl
        title: Título de la sección
        row: Fila donde escribir
        font_size: Tamaño de fuente
        
    Returns:
        int: Siguiente fila disponible
    """
    worksheet[f'A{row}'] = title
    worksheet[f'A{row}'].font = Font(bold=True, size=font_size)
    return row + 1


def write_key_value_pair(worksheet, key: str, value: str, row: int, 
                        border=BORDER) -> int:
    """
    Escribir par clave-valor (información básica).
    
    Args:
        worksheet: Worksheet de openpyxl
        key: Clave (columna A)
        value: Valor (columna B)
        row: Fila donde escribir
        border: Border a aplicar
        
    Returns:
        int: Siguiente fila disponible
    """
    worksheet[f'A{row}'] = key
    worksheet[f'B{row}'] = value
    worksheet[f'A{row}'].font = Font(bold=True)
    for col in range(1, 3):
        worksheet.cell(row, col).border = border
        worksheet.cell(row, col).alignment = Alignment(horizontal='left', vertical='center')
    return row + 1

