"""Procesamiento de niveles"""

from api.core.models import TelemetryRecord


def nivel_mt(value, base, point_catchment_id=None, position=None):
    """Calcular nivel en metros"""
    try:
        calculate = float(value) / float(base)

        # Si el nivel es negativo O es cero (error de lectura), buscar estrategia de corrección
        if (calculate < 0 or calculate == 0) and point_catchment_id:
            # Lógica ELIMINADA: No forzar valor a position-1 (que da freatico=1)
            # Se prefiere mostrar 0 o el histórico real si la lectura falla
            
            print(f"Nivel {'negativo' if calculate < 0 else 'cero'} detectado. No se usará corrección para evitar perpetuar datos erróneos.")
            return "00.00"

        if calculate < 0 or abs(calculate) >= 1000:
            print("Calculated value exceeds the allowed precision and scale")
            return "00.00"
        return "{:.2f}".format(calculate)
    except (ValueError, ZeroDivisionError) as e:
        print(f"Error: {e}")
        return "00.00"


def water_table(value, position):
    """Calcular nivel freático"""
    try:
        # Validar que position (d3) sea válido
        if not position or float(position if position else 0) <= 0:
            print(f"Error: posición de nivel (d3) no válida: {position}")
            return "00.00"

        calculate = float(position) - float(value)
        if calculate < 0 or abs(calculate) >= 1000:
            print("Calculated value exceeds the allowed precision and scale")
            return "00.00"
        return "{:.2f}".format(calculate)
    except ValueError as e:
        print(f"Error: {e}")
        return "00.00"
