from datetime import datetime
from api.core.models import InteractionDetail
import pytz

def instantaneous_flow_calculate(value, convert_to_lt, n_base):
    """
    Calculate the instantaneous flow based on the given value.

    Args:
        value (int or float or str): The value to be used in the calculation.
        convert_to_lt (bool): Flag to convert the value to liters.
        n_base: The base for division (expected to be int or float).

    Returns:
        float: The calculated instantaneous flow value, or 0.0 if any error or invalid input.
    """
    try:
        # PRIMER PASO CRUCIAL: Asegurarse de que 'value' no sea None y sea convertible a float.
        # Capturamos TypeError (para None) y ValueError (para cadenas no numéricas)
        if value is None:
            # Si el valor es None, lo tratamos como 0.0 desde el principio.
            # Puedes imprimir una advertencia si lo deseas:
            # print("Advertencia: 'value' es None. Asumiendo 0.0.")
            value = 0.0
        else:
            # Si no es None, intentamos convertirlo a float.
            # Si falla (ej. si value es "abc"), lanzará un ValueError.
            value = float(value)

        # Ahora 'value' está garantizado como un float (o 0.0 si era None o no convertible)

        if value < 1.0:
            return 0.0

        if convert_to_lt:
            value /= 3.6

        # Manejo de n_base para evitar ZeroDivisionError y posibles errores de tipo si n_base es None
        if not isinstance(n_base, (int, float)):
            # Si n_base no es un número, o si es None (is None ya es cubierto por not isinstance)
            print(f"Error: n_base '{n_base}' no es un número válido. Retornando 0.0.")
            return 0.0
        elif n_base == 0:
            # Si n_base es cero, evitamos la división por cero.
            print("Error: n_base es cero. No se puede dividir por cero. Retornando 0.0.")
            return 0.0

        # Si n_base es válido y no cero, procedemos con la división.
        value = float(value / n_base)

        # Ensure the value is within the required precision and scale
        if abs(value) >= 1000:
            print("Calculated value exceeds the allowed precision and scale")
            return 0.0

        # Formatear el float a 2 decimales y devolverlo como float
        return float(f"{value:.2f}")

    except ValueError as e:
        # Este except captura específicamente errores de conversión a float (ej. value = "not_a_number")
        print(f"Error de conversión: {e}")
        return 0.0
    except Exception as e:
        # Este except captura cualquier otro error inesperado que pueda surgir en la lógica
        # (aunque con las verificaciones añadidas, es menos probable).
        print(f"Error inesperado: {e}")
        return 0.0


def instantaneous_flow(value, convert_to_lt, scale_divisor=None):
    """
    Calculate the instantaneous flow based on the given value.

    Args:
        value (int or float or str): The value to be used in the calculation.
        convert_to_lt (bool): Flag to convert the value to liters.
        scale_divisor (int or float): Optional scale divisor from calculate_nivel field.

    Returns:
        float: The calculated instantaneous flow value.
    """
    try:
        value = float(value)
        if value < 1.0:
            return 0.0
            
        # APLICAR DIVISOR DE ESCALA PARA CAUDAL usando calculate_nivel
        # Si scale_divisor tiene un valor válido, dividir el caudal por ese valor
        if scale_divisor and isinstance(scale_divisor, (int, float)) and scale_divisor > 0:
            print(f"Aplicando divisor de escala para caudal: {value} / {scale_divisor}")
            value = value / float(scale_divisor)
            
        if convert_to_lt:
            value /= 3.6
            
        # Ensure the value is within the required precision and scale
        if abs(value) >= 1000:
            print("Calculated value exceeds the allowed precision and scale")
            return 0.0
        return float(f"{value:.2f}")
    except ValueError as e:
        print(f"Error: {e}")
        return 0.0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 0.0


def average_flow(point_catchment, total, date_lg):
    """
    Calculate the average flow based on the given point catchment, total, and date.

    Args:
        point_catchment (dict): The catchment point details.
        total (int or float): The total value to be used in the calculation.
        date_lg (datetime): The date and time of the logger.

    Returns:
        float: The calculated average flow value.
    """
    try:
        # Validate input types
        if not isinstance(point_catchment, dict) or "id" not in point_catchment:
            raise ValueError("Invalid point_catchment format")
        if not isinstance(total, (int, float)):
            raise ValueError("Total must be a number")
        if not isinstance(date_lg, datetime):
            raise ValueError("date_lg must be a datetime object")

        # Fetch the last interaction detail
        get_last = InteractionDetail.objects.filter(
            catchment_point=point_catchment["id"]
        ).last()
        if not get_last:
            print("No previous interaction detail found.")
            return 0.0

        # Convert dates to Chile timezone
        chile_tz = pytz.timezone('America/Santiago')
        date_lg = date_lg.astimezone(chile_tz)
        get_last.date_time_medition = get_last.date_time_medition.astimezone(chile_tz)
        get_last.date_time_last_logger = get_last.date_time_last_logger.astimezone(chile_tz)

        # Calculate time difference in seconds
        time_difference = (date_lg - get_last.date_time_medition).total_seconds()
        if time_difference <= 0:
            raise ValueError("Time difference must be positive")

        # Calculate flow
        diff_cubics = int(total) - int(get_last.total)
        
        # Solo calcular caudal si hay diferencia positiva en el totalizado
        # Si diff_cubics <= 0, no hay consumo real, por lo que no debe generarse caudal
        if diff_cubics <= 0:
            # Sin consumo o posible reseteo u overflow del totalizador
            return 0.0
            
        divide = diff_cubics / time_difference
        factor = divide * 1000
        value = round(factor, 2)

        # Ensure value is within the allowed range
        if abs(value) >= 1000:
            print("Calculated value exceeds the allowed range for the database field")
            return 0.0

        return float(f"{value:.2f}")

    except (AttributeError, ValueError, TypeError) as e:
        # Log the exception if needed
        print(f"Error: {e}")
        return 0.0

    except (pytz.UnknownTimeZoneError, OverflowError, ZeroDivisionError) as e:
        print(f"Unexpected error: {e}")
        return 0.0
