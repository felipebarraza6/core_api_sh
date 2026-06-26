"""Procesamiento de niveles"""

import logging
from api.core.models import InteractionDetail
from api.cronjobs.telemetry.utils.audit import emit_system_event

logger = logging.getLogger(__name__)


def nivel_mt(value, base, point_catchment_id=None, position=None):
    """Calcular nivel en metros"""
    try:
        # ✅ Validar base antes de dividir
        if base is None or float(base) == 0:
            logger.warning(f"Base inválida (None o 0) para punto {point_catchment_id}. Retornando 00.00")
            if point_catchment_id:
                emit_system_event(
                    event_type="MEASUREMENT_ERROR",
                    point_id=point_catchment_id,
                    title="Base inválida para nivel",
                    message=f"Base inválida (None o 0) para cálculo de nivel. Retornando 00.00.",
                    severity="WARNING",
                    extra_data={
                        "decision": "RECHAZAR",
                        "reason": "El parámetro base (d3 o similar) es nulo o cero, haciendo imposible el cálculo de nivel. Se retorna 00.00 como valor seguro.",
                        "actual_value": base,
                        "expected_range": [0.01, None],
                        "base": base,
                        "source": "api.cronjobs.telemetry.controllers.nivel:nivel_mt",
                    },
                )
            return "00.00"

        calculate = float(value) / float(base)

        # Si el nivel es negativo O es cero (error de lectura), buscar estrategia de corrección
        if (calculate < 0 or calculate == 0) and point_catchment_id:
            # Lógica ELIMINADA: No forzar valor a position-1 (que da freatico=1)
            # Se prefiere mostrar 0 o el histórico real si la lectura falla
            
            logger.warning(f"Nivel {'negativo' if calculate < 0 else 'cero'} detectado. No se usará corrección para evitar perpetuar datos erróneos.")
            emit_system_event(
                event_type="MEASUREMENT_ERROR",
                point_id=point_catchment_id,
                title=f"Nivel {'negativo' if calculate < 0 else 'cero'} detectado",
                message=f"Nivel {'negativo' if calculate < 0 else 'cero'} ({calculate}) detectado. Corregido a 00.00.",
                severity="WARNING",
                extra_data={
                    "decision": "RECHAZAR",
                    "reason": "Un nivel cero o negativo no tiene sentido físico para un pozo con agua. Se corrige a 00.00 para evitar distorsiones en el cálculo del nivel freático.",
                    "actual_value": calculate,
                    "expected_range": [0.01, None],
                    "raw_value": value,
                    "calculate": calculate,
                    "base": base,
                    "corrected_to": "00.00",
                    "source": "api.cronjobs.telemetry.controllers.nivel:nivel_mt",
                },
            )
            return "00.00"

        if calculate < 0:
            logger.warning(f"Nivel negativo ({calculate}) detectado. Corregido a 00.00.")
            if point_catchment_id:
                emit_system_event(
                    event_type="MEASUREMENT_ERROR",
                    point_id=point_catchment_id,
                    title="Nivel negativo detectado",
                    message=f"Nivel calculado ({calculate}) es negativo. Corregido a 00.00.",
                    severity="WARNING",
                    extra_data={
                        "decision": "RECHAZAR",
                        "reason": "Un nivel negativo indica una lectura errónea del sensor o una base mal configurada. Se corrige a 00.00.",
                        "actual_value": calculate,
                        "expected_range": [0.01, None],
                        "calculate": calculate,
                        "source": "api.cronjobs.telemetry.controllers.nivel:nivel_mt",
                    },
                )
            return "00.00"
        return "{:.2f}".format(calculate)
    except (ValueError, ZeroDivisionError) as e:
        logger.error(f"Error: {e}")
        return "00.00"


def water_table(value, position):
    """Calcular nivel freático"""
    try:
        # Validar que position (d3) sea válido
        if not position or float(position if position else 0) <= 0:
            logger.error(f"Error: posición de nivel (d3) no válida: {position}")
            return "00.00"

        calculate = float(position) - float(value)
        if calculate < 0:
            logger.warning(f"Nivel freático negativo ({calculate}) detectado. Corregido a 00.00.")
            return "00.00"
        return "{:.2f}".format(calculate)
    except ValueError as e:
        logger.error(f"Error: {e}")
        return "00.00"
