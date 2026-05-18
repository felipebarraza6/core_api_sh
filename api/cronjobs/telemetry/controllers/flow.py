from datetime import datetime
from api.core.models import InteractionDetail
import pytz
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTES DE PROTECCIÓN ANTI-DISPARO (fallbacks si no hay profile)
# ============================================================================
MAX_FLOW_LS = 150.0           # Máximo caudal razonable en L/s
MAX_TIME_GAP_HOURS = 2        # Si Δt > 2 horas, no calcular (reconexión)
MAX_DIFF_M3_PER_HOUR = 500    # Máximo consumo razonable por hora


def _get_profile_limits(point_catchment: dict):
    """Lee límites configurables del profile, o retorna defaults."""
    profile = point_catchment.get("profile_data_config") if isinstance(point_catchment, dict) else None
    if not profile:
        return MAX_DIFF_M3_PER_HOUR, MAX_FLOW_LS, MAX_TIME_GAP_HOURS
    return (
        float(profile.get("max_diff_m3_per_hour", MAX_DIFF_M3_PER_HOUR) or MAX_DIFF_M3_PER_HOUR),
        float(profile.get("max_flow_ls", MAX_FLOW_LS) or MAX_FLOW_LS),
        float(profile.get("max_time_gap_hours", MAX_TIME_GAP_HOURS) or MAX_TIME_GAP_HOURS),
    )

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



def average_flow(point_catchment, total, date_lg, exclude_id=None, current_logger_dt=None):
    """
    Caudal promedio (L/s) = ((total_actual - total_anterior) / Δt_seg) * 1000
    Δt usa preferentemente la diferencia de date_time_last_logger si está disponible (mayor precisión),
    sino usa date_time_medition.
    """
    try:
        if not isinstance(point_catchment, dict) or "id" not in point_catchment:
            return 0.0
        if not isinstance(total, (int, float)):
            return 0.0
        if not isinstance(date_lg, datetime):
            return 0.0

        chile_tz = pytz.timezone('America/Santiago')
        
        # 1. Normalizar timestamp actual (date_lg / medition)
        if date_lg.tzinfo is None:
            curr_ts = chile_tz.localize(date_lg)
        else:
            curr_ts = date_lg.astimezone(chile_tz)

        # 2. Buscar registro anterior
        query = InteractionDetail.objects.filter(
            catchment_point_id=point_catchment["id"],
            date_time_medition__isnull=False,
            date_time_medition__lt=date_lg
        )
        if exclude_id:
            query = query.exclude(pk=exclude_id)
            
        get_last = query.order_by('-date_time_medition').first()
        
        if not get_last or get_last.total is None:
            return 0.0

        # 3. Calcular Diferencia de Tiempo (Prioridad: Logger > Medition)
        time_difference = 0.0
        used_logger_diff = False

        # Intentar usar fechas del logger si están disponibles (Mejor precisión para retardos)
        if current_logger_dt and isinstance(current_logger_dt, datetime) and get_last.date_time_last_logger:
            try:
                # Normalizar current logger
                if current_logger_dt.tzinfo is None:
                    c_log = chile_tz.localize(current_logger_dt)
                else:
                    c_log = current_logger_dt.astimezone(chile_tz)
                
                # Normalizar prev logger
                if get_last.date_time_last_logger.tzinfo is None:
                    p_log = chile_tz.localize(get_last.date_time_last_logger)
                else:
                    p_log = get_last.date_time_last_logger.astimezone(chile_tz)

                diff_log = (c_log - p_log).total_seconds()
                
                if diff_log > 0:
                    time_difference = diff_log
                    used_logger_diff = True
            except Exception as e:
                print(f"Warning: Error calculating logger diff: {e}")

        # Si no se pudo usar logger (o dio <= 0), usar date_time_medition (Ingesta)
        if time_difference <= 0:
            prev_ts = get_last.date_time_medition
            if prev_ts.tzinfo is None:
                prev_ts = chile_tz.localize(prev_ts)
            else:
                prev_ts = prev_ts.astimezone(chile_tz)
            
            time_difference = (curr_ts - prev_ts).total_seconds()
            
            # Fallback extra: si medition es igual (<=0), intentar logger anterior vs este medition
            # (Caso raro de duplicados de hora pero distinta data)
            if time_difference <= 0:
                alt_prev_ts = get_last.date_time_last_logger
                if alt_prev_ts:
                    if alt_prev_ts.tzinfo is None: alt_prev_ts = chile_tz.localize(alt_prev_ts)
                    else: alt_prev_ts = alt_prev_ts.astimezone(chile_tz)
                    time_difference = (curr_ts - alt_prev_ts).total_seconds()

        if time_difference <= 0:
            return 0.0

        # ====================================================================
        # VALIDACIONES ANTI-DISPARO (Reconexión / Reset)
        # ====================================================================
        max_diff, max_flow, max_gap = _get_profile_limits(point_catchment)
        
        # 4a. Si hay brecha de tiempo muy grande (reconexión después de desconexión)
        if time_difference > (max_gap * 3600):
            logger.info(
                f"⚠️ Punto {point_catchment['id']}: Gap de tiempo grande "
                f"({time_difference/3600:.1f}h > {max_gap}h). "
                f"Caudal se calculará como promedio sobre el gap."
            )
        
        # 4b. Si el registro anterior tenía días sin conexión (logger desconectado)
        if hasattr(get_last, 'days_not_conection') and get_last.days_not_conection and get_last.days_not_conection > 0:
            logger.info(
                f"⚠️ Punto {point_catchment['id']}: Reconexión detectada "
                f"(días sin conexión anterior: {get_last.days_not_conection}). "
                f"Caudal se calculará como promedio sobre el gap."
            )

        # 5. Calcular diferencia de volumen (m3)
        last_total = float(get_last.total)
        diff_cubics = float(total) - last_total

        # Detector de reseteo
        if diff_cubics < 0:
            diff_cubics = float(total)

        if diff_cubics <= 0:
            return 0.0

        # 5b. Validar que el consumo por hora sea razonable
        consumption_per_hour = (diff_cubics / time_difference) * 3600
        if consumption_per_hour > max_diff:
            logger.warning(
                f"🚨 Punto {point_catchment['id']}: Consumo por hora excesivo "
                f"({consumption_per_hour:.0f} m³/h > {max_diff}) - Caudal = 0"
            )
            return 0.0

        # 6. Calcular caudal (L/s)
        value = round((diff_cubics / time_difference) * 1000.0, 2)

        # 6b. Validar caudal máximo razonable
        if value > max_flow:
            logger.warning(
                f"🚨 Punto {point_catchment['id']}: Caudal excesivo "
                f"({value:.2f} L/s > {max_flow}) - Caudal = 0"
            )
            return 0.0

        # Protección contra valores fuera de rango para la BD (max 999.99)
        if abs(value) >= 1000:
            return 0.0

        return value

    except Exception as e:
        logger.error(f"Error in average_flow for point {point_catchment.get('id')}: {str(e)}")
        return 0.0

