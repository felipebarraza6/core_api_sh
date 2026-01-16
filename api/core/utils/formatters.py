"""
Utilidades de formateo compartidas.

Centraliza funciones de formateo de números y cálculos
usados en reportes PDF y Excel.

Este módulo elimina la duplicación de código que existía entre
pdf_generator.py y excel_utils.py.
"""
from decimal import Decimal
from typing import Union, Optional


def format_number_with_thousands(value: Optional[Union[int, float, Decimal]]) -> str:
    """
    Formatear número con separador de miles (punto).

    Args:
        value: Número a formatear. Puede ser None.

    Returns:
        String formateado con puntos como separadores de miles.
        Retorna "0" si value es None.

    Examples:
        >>> format_number_with_thousands(1000)
        '1.000'
        >>> format_number_with_thousands(1234567)
        '1.234.567'
        >>> format_number_with_thousands(None)
        '0'
    """
    if value is None:
        return "0"

    try:
        # Convertir a float para formateo
        num = float(value)
        # Formatear con coma y reemplazar por punto
        return f"{num:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"


def format_decimal(
    value: Optional[Union[int, float, Decimal]],
    decimals: int = 2
) -> str:
    """
    Formatear número decimal con separador de miles y decimales.

    Args:
        value: Número a formatear. Puede ser None.
        decimals: Cantidad de decimales a mostrar (default: 2).

    Returns:
        String formateado con punto como separador de miles
        y coma como separador decimal.
        Retorna "0,00" (o "0,0..." según decimals) si value es None.

    Examples:
        >>> format_decimal(1234.56)
        '1.234,56'
        >>> format_decimal(1234.5678, decimals=3)
        '1.234,568'
        >>> format_decimal(None)
        '0,00'
    """
    if value is None:
        return "0" + "," + "0" * decimals

    try:
        num = float(value)
        # Formatear con coma como separador de miles
        formatted = f"{num:,.{decimals}f}"
        # Reemplazar coma por punto (miles) y punto por coma (decimal)
        # Primero cambiar coma a temporal, luego punto a coma, luego temporal a punto
        formatted = formatted.replace(",", "TEMP")
        formatted = formatted.replace(".", ",")
        formatted = formatted.replace("TEMP", ".")
        return formatted
    except (ValueError, TypeError):
        return "0" + "," + "0" * decimals


def calculate_variation_percentage(
    current: Union[int, float, Decimal],
    previous: Union[int, float, Decimal]
) -> float:
    """
    Calcular porcentaje de variación entre dos valores.

    Args:
        current: Valor actual.
        previous: Valor anterior.

    Returns:
        Porcentaje de variación. Retorna 100.0 si previous es 0 y current > 0,
        retorna 0.0 si ambos son 0.

    Examples:
        >>> calculate_variation_percentage(150, 100)
        50.0
        >>> calculate_variation_percentage(75, 100)
        -25.0
        >>> calculate_variation_percentage(100, 0)
        100.0
        >>> calculate_variation_percentage(0, 0)
        0.0
    """
    try:
        current = float(current)
        previous = float(previous)

        if previous == 0:
            return 100.0 if current > 0 else 0.0

        variation = ((current - previous) / previous) * 100
        return round(variation, 2)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0


def format_percentage(value: Union[int, float, Decimal]) -> str:
    """
    Formatear porcentaje con 2 decimales y símbolo %.

    Args:
        value: Valor del porcentaje.

    Returns:
        String formateado con % al final.

    Examples:
        >>> format_percentage(15.5)
        '15,50%'
        >>> format_percentage(-5.25)
        '-5,25%'
    """
    try:
        num = float(value)
        return f"{num:.2f}".replace(".", ",") + "%"
    except (ValueError, TypeError):
        return "0,00%"
