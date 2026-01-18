import logging
from typing import List, Optional

from api.telemetry.models.catchment_points import CatchmentPoint
from api.telemetry.models.telemetry import CoreVariable

logger = logging.getLogger(__name__)

# Definiciones de variables estándar
DEFAULT_VARIABLE_DEFINITIONS = {
    "total": {
        "name": "Totalizado (m³)",
        "unit": "m³",
        "type_variable": "TOTALIZADO",
        "provider_key": "total",
        "priority": 10,
        "get_configuration": lambda profile: {
            "pulses_factor": (
                float(profile.d1) if profile and profile.d1 else 1000.0
            ),
            "calculate_nivel": False,
        },
    },
    "flow": {
        "name": "Caudal (L/s)",
        "unit": "L/s",
        "type_variable": "CAUDAL_PROMEDIO",
        "priority": 20,
        "get_configuration": lambda profile: {},
    },
    "nivel": {
        "name": "Nivel Freático (m)",
        "unit": "m",
        "type_variable": "NIVEL",
        "provider_key": "level",
        "priority": 30,
        "get_configuration": lambda profile: {
            "calculate_nivel": True,
            "d3": float(profile.d3) if profile and profile.d3 else 0.0,
        },
    },
}


def initialize_default_variables(
    point_id: int,
    variable_types: Optional[List[str]] = None,
    skip_if_scheme_assigned: bool = False,
) -> bool:
    """
    Inicializa las variables estándar para un punto de captación.

    Args:
        point_id: ID del punto de captación
        variable_types: Lista de tipos de variables a crear.
            Opciones: "total", "flow", "nivel".
            Si es None, crea las 3 por defecto.
        skip_if_scheme_assigned: Si True, no crea variables si el punto
            ya tiene un TelemetryScheme asignado (las heredará del esquema).

    Returns:
        True si se crearon las variables exitosamente, False en caso de error.

    Examples:
        # Crear solo totalizado y caudal (sin nivel)
        initialize_default_variables(123, variable_types=["total", "flow"])

        # Crear todas las variables por defecto
        initialize_default_variables(123)

        # No crear variables si tiene esquema asignado
        initialize_default_variables(123, skip_if_scheme_assigned=True)
    """
    try:
        point = CatchmentPoint.objects.get(id=point_id)

        # Si tiene esquema asignado y skip_if_scheme_assigned=True, no crear
        if skip_if_scheme_assigned and point.processing_scheme:
            logger.info(
                f"⏭️  [VARS] Punto {point_id} tiene esquema asignado, "
                "omitiendo creación de variables por defecto"
            )
            return True

        profile = point.data_config_profiles.first()

        # Determinar qué variables crear
        if variable_types is None:
            variable_types = ["total", "flow", "nivel"]

        created_vars = []
        for var_type in variable_types:
            if var_type not in DEFAULT_VARIABLE_DEFINITIONS:
                logger.warning(
                    f"⚠️  [VARS] Tipo de variable desconocido: {var_type}"
                )
                continue

            var_def = DEFAULT_VARIABLE_DEFINITIONS[var_type]

            # Construir defaults
            defaults = {
                "name": var_def["name"],
                "unit": var_def["unit"],
                "type_variable": var_def["type_variable"],
                "priority": var_def["priority"],
            }

            # Agregar provider_key si existe
            if "provider_key" in var_def:
                defaults["provider_key"] = var_def["provider_key"]

            # Agregar configuration si existe función
            if "get_configuration" in var_def:
                defaults["configuration"] = var_def["get_configuration"](profile)

            # Crear o obtener variable
            var, created = CoreVariable.objects.get_or_create(
                point=point,
                internal_code=var_type,
                defaults=defaults,
            )

            if created:
                created_vars.append(var_type)

        if created_vars:
            logger.info(
                f"✅ [VARS] Variables creadas para punto {point_id}: {created_vars}"
            )
        else:
            logger.info(
                f"ℹ️  [VARS] Punto {point_id} ya tenía todas las variables configuradas"
            )

        return True

    except CatchmentPoint.DoesNotExist:
        logger.error(f"❌ [VARS] Punto {point_id} no existe")
        return False
    except Exception as e:
        logger.error(
            f"❌ [VARS] Error inicializando variables para punto {point_id}: {e}"
        )
        return False


def sync_variables_from_scheme(point_id: int) -> bool:
    """
    Copia las variables de un esquema asignado como CoreVariables del punto.

    Útil cuando quieres que un punto tenga copias locales de las variables
    del esquema para poder personalizarlas.

    Args:
        point_id: ID del punto de captación

    Returns:
        True si se sincronizaron exitosamente, False en caso de error.
    """
    try:
        point = CatchmentPoint.objects.get(id=point_id)

        if not point.processing_scheme:
            logger.warning(
                f"⚠️  [VARS] Punto {point_id} no tiene esquema asignado"
            )
            return False

        scheme = point.processing_scheme
        created_count = 0

        for scheme_var in scheme.variables.filter(is_active=True):
            _, created = CoreVariable.objects.get_or_create(
                point=point,
                internal_code=scheme_var.internal_code,
                defaults={
                    "name": scheme_var.name,
                    "unit": scheme_var.unit,
                    "type_variable": scheme_var.type_variable,
                    "provider_key": scheme_var.provider_key,
                    "scale_factor": scheme_var.scale_factor,
                    "offset": scheme_var.offset,
                    "operation": scheme_var.operation,
                    "formula": scheme_var.formula,
                    "sources": scheme_var.sources,
                    "priority": scheme_var.priority,
                    "is_virtual": scheme_var.is_virtual,
                    "min_value": scheme_var.min_value,
                    "max_value": scheme_var.max_value,
                    "configuration": scheme_var.configuration,
                },
            )
            if created:
                created_count += 1

        logger.info(
            f"✅ [VARS] Sincronizadas {created_count} variables del esquema "
            f"'{scheme.name}' al punto {point_id}"
        )
        return True

    except CatchmentPoint.DoesNotExist:
        logger.error(f"❌ [VARS] Punto {point_id} no existe")
        return False
    except Exception as e:
        logger.error(
            f"❌ [VARS] Error sincronizando variables para punto {point_id}: {e}"
        )
        return False
