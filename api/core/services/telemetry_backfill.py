"""
Servicio de backfill histórico desde proveedores de telemetría.
===============================================================

Expone la lógica de recuperación histórica de forma reutilizable:
- Usada por el endpoint /api/telemetry-reprocessor/ (action=backfill, source=providers).
- Usada por el script CLI scripts/backfill_point_range.py.

Soporta detección dinámica de provider según TelemetryProvider:
- handler_name == "tdata"    -> get_data_tdata_history
- handler_name == "tago"     -> get_data_tago_history
- handler_name == "thethings" o "generic_json" -> no soportado histórico

Fallback a booleanos legacy:
- point.is_tdata  -> tdata
- point.is_novus  -> tago
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytz

from api.core.models import (
    CatchmentPoint,
    InteractionDetail,
    ProfileDataConfigCatchment,
    SchemesCatchment,
    Variable,
)
from api.cronjobs.telemetry.controllers.backfill_processing import process_backfill_range
from api.cronjobs.telemetry.getters.tdata import get_data_tdata_history
from api.cronjobs.telemetry.getters.tago import get_data_tago_history

logger = logging.getLogger(__name__)

CHILE_TZ = pytz.timezone("America/Santiago")

# Mapeo legacy de booleanos a handler_name
LEGACY_PROVIDER_MAP = {
    "is_tdata": "tdata",
    "is_novus": "tago",
}

def _history_function_for_handler(handler_name: str) -> Optional[Callable]:
    """
    Resuelve la función de historial para un handler_name.
    Se resuelve en tiempo de ejecución para facilitar mocking en tests.
    """
    if handler_name == "tdata":
        return get_data_tdata_history
    elif handler_name == "tago":
        return get_data_tago_history
    return None


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def truncate_to_freq(dt: datetime, freq_min: int) -> datetime:
    """Truncar datetime al bucket de frecuencia."""
    if freq_min == 1:
        return dt.replace(second=0, microsecond=0)
    elif freq_min == 5:
        minute = (dt.minute // 5) * 5
        return dt.replace(minute=minute, second=0, microsecond=0)
    elif freq_min == 10:
        minute = (dt.minute // 10) * 10
        return dt.replace(minute=minute, second=0, microsecond=0)
    elif freq_min == 60:
        return dt.replace(minute=0, second=0, microsecond=0)
    else:
        return dt.replace(second=0, microsecond=0)


def resolve_point_handler_name(point: CatchmentPoint) -> Optional[str]:
    """
    Resuelve el handler_name del provider asociado al punto.

    Orden de resolución:
    1. point.telemetry_provider.handler_name
    2. Booleanos legacy: is_tdata -> "tdata", is_novus -> "tago"
    3. None si no se puede determinar
    """
    if point.telemetry_provider_id and point.telemetry_provider.handler_name:
        return point.telemetry_provider.handler_name

    for flag, handler in LEGACY_PROVIDER_MAP.items():
        if getattr(point, flag, False):
            return handler

    return None


def resolve_variable_handler_name(variable: Variable) -> Optional[str]:
    """
    Resuelve el handler_name del provider asociado a una variable.
    """
    if variable.provider_id and variable.provider.handler_name:
        return variable.provider.handler_name
    return None


def get_provider_history_func(point: CatchmentPoint, variable: Optional[Variable] = None) -> Optional[Callable]:
    """
    Devuelve la función de histórico adecuada para el punto/variable.

    Orden:
    1. Provider explícito de la variable.
    2. Provider explícito del punto.
    3. Fallback a booleanos legacy.
    4. None si no hay soporte de histórico.
    """
    handler_name = None
    source = "variable"

    if variable is not None:
        handler_name = resolve_variable_handler_name(variable)

    if not handler_name:
        source = "point"
        handler_name = resolve_point_handler_name(point)

    if not handler_name:
        return None, None, source

    func = _history_function_for_handler(handler_name)
    if func is None:
        return handler_name, None, source

    return handler_name, func, source


def validate_backfill_request(point: CatchmentPoint) -> Tuple[bool, str]:
    """
    Valida que el punto tenga lo mínimo necesario para un backfill.
    Retorna (ok, mensaje_error).
    """
    profile = point.data_config_profiles.filter(is_telemetry=True).first()
    if not profile:
        return False, f"Punto {point.id} no tiene perfil de telemetría activo"

    point_token = profile.token_service or ""
    if not point_token:
        return False, f"Punto {point.id} no tiene token_service configurado"

    scheme = SchemesCatchment.objects.filter(points_catchment=point).first()
    if not scheme:
        return False, f"Punto {point.id} no tiene esquema de variables"

    variables = list(Variable.objects.filter(scheme_catchment=scheme).select_related("provider"))
    if not variables:
        return False, f"Punto {point.id} no tiene variables configuradas"

    # Verificar que al menos una variable tenga histórico soportado
    detected_handlers = set()
    supported = []
    for var in variables:
        handler_name, func, source = get_provider_history_func(point, var)
        detected_handlers.add(handler_name or "unknown")
        if func:
            supported.append((var, handler_name, func, source))

    if not supported:
        return False, (
            f"Punto {point.id} no tiene provider con histórico soportado. "
            f"Handlers detectados: {', '.join(sorted(detected_handlers)) or 'ninguno'}. "
            f"Soportados: tdata, tago"
        )

    return True, ""


def backfill_point_from_providers(
    point: CatchmentPoint,
    start_dt: datetime,
    end_dt: datetime,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Recupera datos históricos de proveedores para un punto y rango, y opcionalmente
    los guarda en InteractionDetail y ejecuta el procesamiento en cascada.

    Args:
        point: instancia de CatchmentPoint.
        start_dt: datetime con timezone (inicio del rango, inclusive).
        end_dt: datetime con timezone (fin del rango, exclusive).
        dry_run: si True, solo simula y no escribe en BD.

    Returns:
        Dict con metadata del backfill y contadores.
    """
    point_id = point.id

    ok, error_msg = validate_backfill_request(point)
    if not ok:
        raise ValueError(error_msg)

    profile = point.data_config_profiles.filter(is_telemetry=True).first()
    point_token = profile.token_service or ""
    scheme = SchemesCatchment.objects.filter(points_catchment=point).first()
    variables = list(Variable.objects.filter(scheme_catchment=scheme).select_related("provider"))

    freq_str = point.frecuency or "60"
    try:
        freq_min = int(freq_str)
    except ValueError:
        freq_min = 60

    # Resolver función de histórico para cada variable
    var_configs = []
    for var in variables:
        handler_name, func, source = get_provider_history_func(point, var)
        if func:
            var_configs.append({
                "variable": var,
                "handler_name": handler_name,
                "history_func": func,
                "source": source,
            })

    detected_provider = var_configs[0]["handler_name"] if var_configs else None

    # Buckets existentes en el rango
    existing = set(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=start_dt,
            date_time_medition__lt=end_dt,
        ).values_list("date_time_medition", flat=True)
    )
    existing_strs = {dt.strftime("%Y-%m-%dT%H:%M:%S") for dt in existing}

    # Consultar histórico por variable y agrupar en buckets
    bucket_data: Dict[str, Dict[str, Dict[str, Any]]] = {}
    fetch_errors = []

    utc = pytz.utc
    start_utc = start_dt.astimezone(utc).replace(tzinfo=None)
    end_utc = end_dt.astimezone(utc).replace(tzinfo=None)

    for config in var_configs:
        var = config["variable"]
        func = config["history_func"]
        handler_name = config["handler_name"]
        str_variable = var.str_variable
        var_type = var.type_variable

        # Provider a pasar al getter: preferir variable.provider, luego point.telemetry_provider
        provider = var.provider if var.provider_id else point.telemetry_provider

        try:
            history = func(
                provider=provider,
                token_service=point_token,
                str_variable=str_variable,
                start_dt=start_utc,
                end_dt=end_utc,
                limit=10000,
            )
        except Exception as e:
            msg = f"Error consultando {handler_name}/{str_variable}: {e}"
            logger.error(msg)
            fetch_errors.append(msg)
            continue

        logger.info(
            f"[BACKFILL] punto={point_id} provider={handler_name} "
            f"variable={str_variable} ({var_type}) registros={len(history)}"
        )

        for item in history:
            item_dt = datetime.strptime(item["date_time"], "%Y-%m-%dT%H:%M:%S")
            item_dt = utc.localize(item_dt).astimezone(CHILE_TZ)
            bucket = truncate_to_freq(item_dt, freq_min)
            bucket_str = bucket.strftime("%Y-%m-%dT%H:%M:%S")

            if bucket_str not in bucket_data:
                bucket_data[bucket_str] = {}

            # Para cada bucket y tipo de variable, tomar el valor del timestamp más reciente
            existing_ts = bucket_data[bucket_str].get(var_type, {}).get("ts_ms", 0)
            if item["ts_ms"] > existing_ts:
                bucket_data[bucket_str][var_type] = {
                    "value": item["value"],
                    "ts_ms": item["ts_ms"],
                    "ts_str": item["date_time"],
                }

    if not bucket_data:
        return {
            "success": True,
            "point_id": point_id,
            "provider": detected_provider,
            "range": f"{start_dt.strftime('%Y-%m-%dT%H:%M:%S')} → {end_dt.strftime('%Y-%m-%dT%H:%M:%S')}",
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 0,
            "processing": {},
            "fetch_errors": fetch_errors,
            "sample": [],
            "message": "Sin datos históricos disponibles en el rango",
        }

    creados = 0
    actualizados = 0
    errores = 0
    sample = []

    for bucket_str in sorted(bucket_data.keys()):
        vars_in_bucket = bucket_data[bucket_str]

        created_register = {
            "date_time_medition": bucket_str,
            "is_error": False,
            "is_partial": False,
            "variable_details": [],
            "variable_values": {},
        }

        # Timestamp del logger: el más reciente entre variables del bucket
        best_ts = None
        for info in vars_in_bucket.values():
            if best_ts is None or info["ts_str"] > best_ts:
                best_ts = info["ts_str"]
        created_register["date_time_last_logger"] = best_ts

        for var in variables:
            var_type = var.type_variable
            if var_type not in vars_in_bucket:
                continue
            info = vars_in_bucket[var_type]
            value = info["value"]

            if var_type == "TOTALIZADO":
                try:
                    created_register["pulses"] = int(float(value))
                except (ValueError, TypeError):
                    created_register["pulses"] = 0
            elif var_type == "CAUDAL":
                try:
                    created_register["flow"] = round(float(value), 2)
                except (ValueError, TypeError):
                    created_register["flow"] = 0.0
            elif var_type == "NIVEL":
                try:
                    created_register["nivel"] = round(float(value), 2)
                except (ValueError, TypeError):
                    created_register["nivel"] = 0.0

            created_register["variable_details"].append({
                "str_variable": var.str_variable,
                "type_variable": var_type,
                "value": value,
                "success": True,
            })
            created_register["variable_values"][str(var.id)] = value

        if dry_run:
            if bucket_str in existing_strs:
                actualizados += 1
            else:
                creados += 1
            if len(sample) < 10:
                sample.append({
                    "bucket": bucket_str,
                    "action": "update" if bucket_str in existing_strs else "create",
                    "data": created_register,
                })
            continue

        try:
            obj, created = InteractionDetail.objects.update_or_create(
                catchment_point_id=point_id,
                date_time_medition=bucket_str,
                defaults=created_register,
            )
            if created:
                creados += 1
            else:
                actualizados += 1
            if len(sample) < 10:
                sample.append({
                    "bucket": bucket_str,
                    "action": "update" if not created else "create",
                    "interaction_detail_id": obj.id,
                    "data": created_register,
                })
        except Exception as e:
            logger.error(f"[BACKFILL] Error guardando bucket {bucket_str} punto {point_id}: {e}")
            errores += 1
            fetch_errors.append(str(e))

    processing_result = {}
    if not dry_run and (creados + actualizados) > 0:
        logger.info(f"[BACKFILL] punto={point_id} iniciando procesamiento en cascada...")
        processing_result = process_backfill_range(point, start_dt, end_dt)

    return {
        "success": True,
        "point_id": point_id,
        "provider": detected_provider,
        "range": f"{start_dt.strftime('%Y-%m-%dT%H:%M:%S')} → {end_dt.strftime('%Y-%m-%dT%H:%M:%S')}",
        "records_created": creados,
        "records_updated": actualizados,
        "records_failed": errores,
        "processing": processing_result,
        "fetch_errors": fetch_errors,
        "sample": sample,
    }
