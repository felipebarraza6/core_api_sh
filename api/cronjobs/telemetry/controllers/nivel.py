"""Procesamiento de niveles"""

from api.core.models import InteractionDetail


def nivel_mt(value, base, point_catchment_id=None, position=None):
    """Calcular nivel en metros"""
    try:
        calculate = float(value) / float(base)

        # Si el nivel es negativo O es cero (error de lectura), buscar estrategia de corrección
        if (calculate < 0 or calculate == 0) and point_catchment_id:
            # Si tenemos position (d3), usar position - 1 para que water_table = 1
            if position and float(position) > 1:
                nivel_corregido = float(position) - 1
                print(f"Nivel {'negativo' if calculate < 0 else 'cero'} corregido usando position-1: {nivel_corregido} (water_table será 1)")
                return "{:.2f}".format(nivel_corregido)
            
            # Fallback: buscar el nivel más alto registrado si no hay position válido
            nivel_mas_alto = (
                InteractionDetail.objects.filter(catchment_point_id=point_catchment_id)
                .exclude(nivel__isnull=True)
                .order_by("-nivel")
                .first()
            )

            if nivel_mas_alto:
                print(
                    f"Nivel {'negativo' if calculate < 0 else 'cero'} corregido usando valor más alto: {nivel_mas_alto.nivel}"
                )
                return "{:.2f}".format(nivel_mas_alto.nivel)
            else:
                print("Nivel inválido y no hay registros previos ni position válido, usando 0")
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
