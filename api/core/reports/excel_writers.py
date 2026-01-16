"""
Funciones para escribir datos específicos en Excel
==================================================

Funciones especializadas para escribir diferentes tipos de datos:
- Información del pozo (datos estáticos)
- Información DGA
- Indicadores
- Tablas de registros detallados
"""

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from typing import List, Dict, Optional
from api.core.models import CatchmentPoint, InteractionDetail
from .excel_utils import (
    HEADER_FILL, HEADER_FONT, BORDER, 
    write_section_title, write_key_value_pair, 
    create_header_row, write_data_row, format_decimal, format_number_with_thousands
)


def write_pozo_info(worksheet, profile, point, row: int) -> int:
    """
    Escribir información estática del pozo.
    
    Args:
        worksheet: Worksheet de openpyxl
        profile: ProfileDataConfigCatchment
        point: CatchmentPoint (para obtener tipo de caudal)
        row: Fila inicial donde escribir
        
    Returns:
        int: Siguiente fila disponible
    """
    if not profile:
        return row
    
    row = write_section_title(worksheet, "Datos Estáticos del Pozo", row)
    
    # Encabezados
    pozo_headers = ['Parámetro', 'Valor']
    row = create_header_row(worksheet, pozo_headers, row)
    
    # Obtener tipo de caudal
    from api.core.models import Variable
    variables = Variable.objects.filter(scheme_catchment__points_catchment=point)
    has_caudal_promedio = variables.filter(type_variable="CAUDAL_PROMEDIO").exists()
    tipo_caudal = "Caudal Promedio" if has_caudal_promedio else "Caudal Instantáneo"
    
    # Datos del pozo
    pozo_info = [
        ['d1 - Profundidad', f"{float(profile.d1)} m" if profile.d1 else 'Sin registros'],
        ['d2 - Posicionamiento Bomba', f"{float(profile.d2)} m" if profile.d2 else 'Sin registros'],
        ['d3 - Posicionamiento Nivel', f"{float(profile.d3)} m" if profile.d3 else 'Sin registros'],
        ['d4 - Diámetro Ducto Salida', f"{float(profile.d4)} pulg" if profile.d4 else 'Sin registros'],
        ['d5 - Diámetro Flujómetro', f"{float(profile.d5)} pulg" if profile.d5 else 'Sin registros'],
        ['d6 - Caudalímetro Inicial', str(profile.d6) if profile.d6 else 'Sin registros'],
        ['Tipo de Caudal', tipo_caudal],  # ✅ Agregar tipo de caudal
        ['Fecha Inicio Telemetría', profile.date_start_telemetry.strftime('%Y-%m-%d') if profile.date_start_telemetry else 'Sin registros'],
        ['Fecha Acta Entrega', profile.date_delivery_act.strftime('%Y-%m-%d') if profile.date_delivery_act else 'Sin registros'],
        ['Telemetría Activa', 'Sí' if profile.is_telemetry else 'No'],
    ]
    
    for info in pozo_info:
        row = write_key_value_pair(worksheet, info[0], info[1], row)
    
    return row + 1


def write_dga_info(worksheet, dga_config, point: CatchmentPoint, row: int) -> int:
    """
    Escribir información DGA del punto.
    
    Args:
        worksheet: Worksheet de openpyxl
        dga_config: DgaDataConfigCatchment
        point: CatchmentPoint
        row: Fila inicial donde escribir
        
    Returns:
        int: Siguiente fila disponible
    """
    if not dga_config or not dga_config.send_dga:
        return row
    
    row = write_section_title(worksheet, "Información General DGA", row)
    
    # Obtener último voucher DGA
    ultimo_voucher = InteractionDetail.objects.filter(
        catchment_point=point,
        n_voucher__isnull=False
    ).exclude(n_voucher__exact='').order_by('-date_time_medition').first()
    
    voucher_dga = ultimo_voucher.n_voucher if ultimo_voucher and ultimo_voucher.n_voucher else '-'
    
    # Información DGA (sin Voucher DGA, y "DGA Región" -> "Región")
    dga_info = [
        ['Estándar', dga_config.get_standard_display() if hasattr(dga_config, 'get_standard_display') else dga_config.standard],
        ['Tipo DGA', dga_config.get_type_dga_display() if hasattr(dga_config, 'get_type_dga_display') else dga_config.type_dga],
        ['Código Obra', dga_config.code_dga or 'Sin registros'],
        ['Caudal Otorgado', f"{format_decimal(dga_config.flow_granted_dga, 2)} L/s" if dga_config.flow_granted_dga else 'Sin registros'],
        ['Total Otorgado', f"{format_number_with_thousands(dga_config.total_granted_dga)} m³" if dga_config.total_granted_dga else 'Sin registros'],
        ['SHAC', dga_config.shac or 'Sin registros'],
        ['Región', dga_config.region_dga or 'Sin registros'],  # ✅ Cambiado de "DGA Región" a "Región"
    ]
    
    for info in dga_info:
        row = write_key_value_pair(worksheet, info[0], info[1], row)
    
    return row + 1


def write_indicators_table(worksheet, indicators: List[List[str]], row: int) -> int:
    """
    Escribir tabla de indicadores.
    
    Args:
        worksheet: Worksheet de openpyxl
        indicators: Lista de indicadores [['Nombre', 'Valor'], ...]
        row: Fila inicial donde escribir
        
    Returns:
        int: Siguiente fila disponible
    """
    headers = ['Indicador', 'Valor']
    row = create_header_row(worksheet, headers, row)
    
    for indicator in indicators:
        row = write_data_row(worksheet, indicator, row, bold_first_col=True)
    
    return row


def write_dga_records_table(worksheet, dga_records: List[InteractionDetail], 
                           month_name: str, row: int) -> int:
    """
    Escribir tabla de registros enviados a DGA.
    
    Args:
        worksheet: Worksheet de openpyxl
        dga_records: Lista de registros InteractionDetail
        month_name: Nombre del mes (para título)
        row: Fila inicial donde escribir
        
    Returns:
        int: Siguiente fila disponible
    """
    if not dga_records:
        return row
    
    row = write_section_title(worksheet, f"Últimos 5 Registros Enviados a DGA - {month_name}", row)
    
    dga_headers = ['ID', 'Fecha Medición', 'Fecha Logger', 'Total (m³)', 'Caudal (L/s)', 'Nivel (m)', 'Voucher DGA']
    row = create_header_row(worksheet, dga_headers, row)
    
    for dga_rec in dga_records:
        logger_date = dga_rec.date_time_last_logger.strftime('%Y-%m-%d %H:%M:%S') if dga_rec.date_time_last_logger else 'Sin registros'
        voucher_value = dga_rec.n_voucher if dga_rec.n_voucher else '-'
        
        data = [
            dga_rec.id,  # ✅ ID del registro para referencia
            dga_rec.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if dga_rec.date_time_medition else 'Sin registros',
            logger_date,
            int(float(dga_rec.total)) if dga_rec.total else 0,
            float(dga_rec.flow) if dga_rec.flow else 0,
            float(dga_rec.nivel) if dga_rec.nivel else 0,
            voucher_value,
        ]
        row = write_data_row(worksheet, data, row)
    
    return row + 1


def write_detail_records_table(worksheet, records: List[InteractionDetail], 
                               headers: List[str], row: int, 
                               calculate_flow_func=None) -> int:
    """
    Escribir tabla de registros detallados.
    
    Args:
        worksheet: Worksheet de openpyxl
        records: Lista de registros InteractionDetail
        headers: Lista de encabezados
        row: Fila inicial donde escribir
        calculate_flow_func: Función opcional para calcular flow dinámicamente
        
    Returns:
        int: Siguiente fila disponible
    """
    detail_start_row = row
    row = create_header_row(worksheet, headers, row)
    
    for record in records:
        logger_date = record.date_time_last_logger.strftime('%Y-%m-%d %H:%M:%S') if record.date_time_last_logger else 'Sin registros'
        voucher_value = record.n_voucher if record.n_voucher else '-'
        
        # Calcular flow si se proporciona función
        flow_value = float(record.flow) if record.flow else 0.0
        if calculate_flow_func:
            flow_value = calculate_flow_func(record) or flow_value
        
        data = [
            record.date_time_medition.strftime('%Y-%m-%d %H:%M:%S') if record.date_time_medition else 'Sin registros',
            logger_date,
            int(float(record.total)) if record.total else 0,
            flow_value,
            float(record.nivel) if record.nivel else 0,
            float(record.total_diff) if record.total_diff else 0,
            int(record.pulses) if record.pulses else 0,
            float(record.water_table) if record.water_table else 0,
            voucher_value,
        ]
        row = write_data_row(worksheet, data, row)
    
    return row, detail_start_row

