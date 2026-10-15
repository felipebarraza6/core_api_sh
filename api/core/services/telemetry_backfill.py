"""
Servicio de backfill histórico desde proveedores de telemetría.
===============================================================

Expone la lógica de recuperación histórica de forma reutilizable:
- Usada por el endpoint /api/ik/telemetry/backfill/
- Usada por el endpoint /api/telemetry-reprocessor/ (action=backfill, source=providers).
- Usada por el script CLI scripts/backfill_point_range.py.

Soporta detección dinámica de provider según TelemetryProvider:
- handler_name == "tdata"    -> get_data_tdata_history
- handler_name == "tago"     -> get_data_tago_history
- handler_name == "thethings" o "generic_json" -> no soportado histórico

Fallback a booleanos legacy:
- point.is_tdata  -> tdata
- point.is_novus  -> tago

Modo seguro (safe=True, default)
--------------------------------
Por cada hora con dato del proveedor:

1. INSERT si no existe fila para (punto, hora).
2. UPDATE solo si la fila existente es claramente errónea o réplica congelada
   (ver criterio abajo) y NO tiene comprobante DGA.
3. SKIP en cualquier otro caso, con motivo explícito.

Criterio de update (réplica congelada / error)
---------------------------------------------
Una fila existente es elegible para update sii:

- NO tiene ``n_voucher`` DGA válido (comprobante aceptado), Y
- El proveedor trae dato para ese bucket, Y
- Se cumple AL MENOS una de:
  a) ``is_error=True``
  b) Los pulsos guardados son idénticos a los del registro inmediatamente
     anterior (réplica del valor previo) Y los pulsos del proveedor difieren
  c) ``date_time_last_logger`` es idéntico al del registro anterior Y los
     pulsos del proveedor difieren

Si los pulsos (y la hora de logger normalizada) ya coinciden con el proveedor,
se omite (idempotencia: segunda corrida no cambia nada).

Nunca se toca ``send_dga`` ni ``n_voucher``. El recálculo de totales/caudal/
nivel/diffs se limita a las filas insertadas/actualizadas. No se encola nada
para envío DGA.

Dry-run (dry_run=True, default)
-------------------------------
Simula insert/update/skip por hora sin escribir en BD.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pytz

from api.core.models import (
    CatchmentPoint,
    InteractionDetail,
    SchemesCatchment,
    Variable,
)
from api.cronjobs.telemetry.controllers.backfill_processing import process_backfill_range
from api.cronjobs.telemetry.getters.tdata import get_data_tdata_history
from api.cronjobs.telemetry.getters.tago import get_data_tago_history
from api.cronjobs.telemetry.utils.connection import utc_iso_to_chile_str

logger = logging.getLogger(__name__)

CHILE_TZ = pytz.timezone("America/Santiago")

# Motivos de decisión por hora (API / logs)
REASON_INSERT = "missing_hour"
REASON_UPDATE_ERROR = "is_error"
REASON_UPDATE_FROZEN_PULSES = "frozen_replica_pulses"
REASON_UPDATE_FROZEN_LOGGER = "frozen_replica_logger_ts"
REASON_SKIP_DGA = "dga_voucher"
REASON_SKIP_VALID = "existing_valid"
REASON_SKIP_MATCHES = "already_matches"

LEGACY_PROVIDER_MAP = {
    "is_tdata": "tdata",
    "is_novus": "tago",
}

# Providers cuyo date_time de histórico llega en UTC (texto sin offset).
UTC_HISTORY_HANDLERS = frozenset({"tago"})


def _history_function_for_handler(handler_name: str) -> Optional[Callable]:
    """Resuelve la función de historial para un handler_name (lazy para mocks)."""
    if handler_name == "tdata":
        return get_data_tdata_history
    if handler_name == "tago":
        return get_data_tago_history
    return None


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def truncate_to_freq(dt: datetime, freq_min: int) -> datetime:
    """Truncar datetime al bucket de frecuencia."""
    if freq_min == 1:
        return dt.replace(second=0, microsecond=0)
    if freq_min == 5:
        minute = (dt.minute // 5) * 5
        return dt.replace(minute=minute, second=0, microsecond=0)
    if freq_min == 10:
        minute = (dt.minute // 10) * 10
        return dt.replace(minute=minute, second=0, microsecond=0)
    if freq_min == 60:
        return dt.replace(minute=0, second=0, microsecond=0)
    return dt.replace(second=0, microsecond=0)


def has_dga_voucher(record: Optional[InteractionDetail]) -> bool:
    """True si el registro ya fue aceptado por la DGA con comprobante."""
    if record is None:
        return False
    voucher = getattr(record, "n_voucher", None)
    if voucher is None:
        return False
    text = str(voucher).strip()
    return bool(text) and text not in ("None", "No se pudo obtener el comprobante")


def resolve_point_handler_name(point: CatchmentPoint) -> Optional[str]:
    """
    Resuelve el handler_name del provider asociado al punto.

    Orden: telemetry_provider → booleanos legacy → None.
    """
    if point.telemetry_provider_id and point.telemetry_provider.handler_name:
        return point.telemetry_provider.handler_name

    for flag, handler in LEGACY_PROVIDER_MAP.items():
        if getattr(point, flag, False):
            return handler
    return None


def resolve_variable_handler_name(variable: Variable) -> Optional[str]:
    """Resuelve el handler_name del provider asociado a una variable."""
    if variable.provider_id and variable.provider.handler_name:
        return variable.provider.handler_name
    return None


def get_provider_history_func(
    point: CatchmentPoint, variable: Optional[Variable] = None
) -> Tuple[Optional[str], Optional[Callable], str]:
    """
    Devuelve (handler_name, history_func, source) para el punto/variable.

    source: "variable" | "point"
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
    return handler_name, func, source


def validate_backfill_request(point: CatchmentPoint) -> Tuple[bool, str]:
    """Valida que el punto tenga lo mínimo necesario para un backfill."""
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


def _bucket_str(dt: datetime) -> str:
    """Clave de bucket siempre en pared de hora Chile (nunca UTC crudo)."""
    if isinstance(dt, str):
        return dt[:19]
    if dt.tzinfo is not None:
        dt = dt.astimezone(CHILE_TZ)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_chile_bucket(bucket_str: str) -> datetime:
    """Parsea 'YYYY-MM-DDTHH:MM:SS' como datetime aware en America/Santiago."""
    naive = datetime.strptime(bucket_str[:19], "%Y-%m-%dT%H:%M:%S")
    if naive.tzinfo is not None:
        return naive.astimezone(CHILE_TZ)
    return CHILE_TZ.localize(naive)


def _chile_dt_from_history_item(item: Dict[str, Any], handler_name: str) -> datetime:
    """
    Datetime aware en hora de Chile a partir de un ítem de histórico.

    Preferimos ``ts_ms`` (epoch absoluto, válido para Tago y TDATA).
    Fallback: parsear ``date_time`` (UTC para tago, local para tdata).
    """
    ts_ms = item.get("ts_ms")
    if ts_ms is not None:
        # Via UTC para evitar rarezas de pytz con fromtimestamp(tz=local)
        return datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=pytz.utc).astimezone(CHILE_TZ)

    raw = str(item.get("date_time") or "")
    # Solo reinterpretar como UTC si el texto trae sufijo Z (crudo Tago).
    # get_data_tago_history ya entrega date_time en hora de Chile.
    if raw.endswith("Z") or (handler_name in UTC_HISTORY_HANDLERS and "Z" in raw):
        converted = utc_iso_to_chile_str(raw if raw.endswith("Z") else f"{raw}Z")
        if converted:
            naive = datetime.strptime(converted, "%Y-%m-%dT%H:%M:%S")
            return CHILE_TZ.localize(naive)

    naive = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
    return CHILE_TZ.localize(naive)


def _logger_str_from_item(item: Dict[str, Any], handler_name: str) -> str:
    """Hora de logger en Chile (YYYY-MM-DDTHH:MM:SS) desde ítem de histórico."""
    chile_dt = _chile_dt_from_history_item(item, handler_name)
    return chile_dt.strftime("%Y-%m-%dT%H:%M:%S")


def _snapshot_record(rec: Optional[InteractionDetail]) -> Optional[Dict[str, Any]]:
    if rec is None:
        return None
    logger_ts = rec.date_time_last_logger
    if logger_ts is not None and logger_ts.tzinfo is not None:
        logger_ts = logger_ts.astimezone(CHILE_TZ)
    return {
        "id": rec.id,
        "pulses": rec.pulses,
        "flow": float(rec.flow) if rec.flow is not None else None,
        "nivel": float(rec.nivel) if rec.nivel is not None else None,
        "total": rec.total,
        "is_error": bool(rec.is_error),
        "send_dga": bool(rec.send_dga),
        "n_voucher": rec.n_voucher,
        "date_time_last_logger": (
            logger_ts.strftime("%Y-%m-%dT%H:%M:%S") if logger_ts else None
        ),
    }


def _pulses_equal(a, b) -> bool:
    try:
        if a is None or b is None:
            return a is None and b is None
        return int(a) == int(b)
    except (TypeError, ValueError):
        return False


def _logger_equal(existing: InteractionDetail, new_logger_str: Optional[str]) -> bool:
    if not new_logger_str:
        return existing.date_time_last_logger is None
    if not existing.date_time_last_logger:
        return False
    existing_str = _bucket_str(existing.date_time_last_logger)
    return existing_str == new_logger_str


def decide_bucket_action(
    existing: Optional[InteractionDetail],
    previous: Optional[InteractionDetail],
    new_pulses: Optional[int],
    new_logger_str: Optional[str],
    safe: bool,
) -> Tuple[str, str]:
    """
    Decide acción para un bucket: (action, reason).

    action ∈ {"insert", "update", "skip"}
    """
    if existing is None:
        return "insert", REASON_INSERT

    if has_dga_voucher(existing):
        return "skip", REASON_SKIP_DGA

    # Idempotencia: ya coincide con el proveedor
    if _pulses_equal(existing.pulses, new_pulses) and _logger_equal(existing, new_logger_str):
        return "skip", REASON_SKIP_MATCHES

    if existing.is_error:
        return "update", REASON_UPDATE_ERROR

    # Réplica congelada: mismos pulsos que la hora anterior, proveedor distinto
    if (
        previous is not None
        and new_pulses is not None
        and _pulses_equal(existing.pulses, previous.pulses)
        and not _pulses_equal(existing.pulses, new_pulses)
    ):
        return "update", REASON_UPDATE_FROZEN_PULSES

    # Réplica congelada: misma marca de logger que la hora anterior
    if (
        previous is not None
        and existing.date_time_last_logger
        and previous.date_time_last_logger
        and existing.date_time_last_logger == previous.date_time_last_logger
        and new_pulses is not None
        and not _pulses_equal(existing.pulses, new_pulses)
    ):
        return "update", REASON_UPDATE_FROZEN_LOGGER

    if safe:
        return "skip", REASON_SKIP_VALID

    # Modo legacy (safe=False): actualizar filas sin voucher
    return "update", "unsafe_overwrite"


def _build_register_payload(
    bucket_str: str,
    vars_in_bucket: Dict[str, Dict[str, Any]],
    variables: List[Variable],
    handler_name: str,
) -> Dict[str, Any]:
    """Arma el dict de campos a persistir (sin send_dga / n_voucher)."""
    created_register: Dict[str, Any] = {
        "date_time_medition": bucket_str,
        "is_partial": False,
        "variable_details": [],
        "variable_values": {},
    }

    best_logger = None
    best_ts_ms = -1
    for info in vars_in_bucket.values():
        ts_ms = info.get("ts_ms") or 0
        if ts_ms >= best_ts_ms:
            best_ts_ms = ts_ms
            best_logger = _logger_str_from_item(
                {"ts_ms": ts_ms, "date_time": info.get("ts_str")},
                handler_name,
            )
    created_register["date_time_last_logger"] = best_logger

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

    # Solo forzamos is_error=False cuando realmente escribimos dato del proveedor
    created_register["is_error"] = False
    return created_register


def backfill_point_from_providers(
    point: CatchmentPoint,
    start_dt: datetime,
    end_dt: datetime,
    dry_run: bool = True,
    safe: bool = True,
) -> Dict[str, Any]:
    """
    Recupera datos históricos de proveedores para un punto y rango.

    Args:
        point: instancia de CatchmentPoint.
        start_dt: datetime con timezone (inicio del rango, inclusive).
        end_dt: datetime con timezone (fin del rango, exclusive).
        dry_run: si True (default), solo simula y no escribe en BD.
        safe: si True (default), solo inserta faltantes y actualiza error/congelados;
              nunca toca filas con voucher DGA.

    Returns:
        Dict con metadata, contadores, by_reason y detalle por hora.
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

    # Filas existentes en el rango (y una previa para criterio de réplica)
    existing_qs = list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=start_dt,
            date_time_medition__lt=end_dt,
        ).order_by("date_time_medition")
    )
    existing_by_str: Dict[str, InteractionDetail] = {
        _bucket_str(r.date_time_medition): r for r in existing_qs
    }

    prior = (
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__lt=start_dt,
        )
        .order_by("-date_time_medition")
        .first()
    )

    # Consultar histórico por variable y agrupar en buckets
    bucket_data: Dict[str, Dict[str, Dict[str, Any]]] = {}
    bucket_handlers: Dict[str, str] = {}
    fetch_errors: List[str] = []

    utc = pytz.utc
    start_utc = start_dt.astimezone(utc).replace(tzinfo=None)
    end_utc = end_dt.astimezone(utc).replace(tzinfo=None)

    for config in var_configs:
        var = config["variable"]
        func = config["history_func"]
        handler_name = config["handler_name"]
        str_variable = var.str_variable
        var_type = var.type_variable
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
            "[BACKFILL] punto=%s provider=%s variable=%s (%s) registros=%s dry_run=%s safe=%s",
            point_id, handler_name, str_variable, var_type, len(history), dry_run, safe,
        )

        for item in history:
            chile_dt = _chile_dt_from_history_item(item, handler_name)
            bucket = truncate_to_freq(chile_dt, freq_min)
            bucket_str = _bucket_str(bucket)

            if bucket_str not in bucket_data:
                bucket_data[bucket_str] = {}
            bucket_handlers[bucket_str] = handler_name

            existing_ts = bucket_data[bucket_str].get(var_type, {}).get("ts_ms", 0)
            if item["ts_ms"] > existing_ts:
                bucket_data[bucket_str][var_type] = {
                    "value": item["value"],
                    "ts_ms": item["ts_ms"],
                    "ts_str": item["date_time"],
                }

    empty_result = {
        "success": True,
        "point_id": point_id,
        "provider": detected_provider,
        "range": f"{start_dt.strftime('%Y-%m-%dT%H:%M:%S')} → {end_dt.strftime('%Y-%m-%dT%H:%M:%S')}",
        "dry_run": dry_run,
        "safe": safe,
        "mode": "dry-run" if dry_run else "applied",
        "records_created": 0,
        "records_updated": 0,
        "records_skipped": 0,
        "records_failed": 0,
        "by_reason": {},
        "processing": {},
        "fetch_errors": fetch_errors,
        "hours": [],
        "sample": [],
        "message": "Sin datos históricos disponibles en el rango",
        "dga_note": (
            "send_dga y n_voucher nunca se modifican; no se encola envío a DGA."
        ),
    }

    if not bucket_data:
        return empty_result

    creados = 0
    actualizados = 0
    omitidos = 0
    errores = 0
    by_reason: Dict[str, int] = {}
    hours_report: List[Dict[str, Any]] = []
    sample: List[Dict[str, Any]] = []
    changed_ids: Set[int] = set()

    # Orden cronológico de buckets + mapa de "previo" (existente o recién decidido)
    # Para el criterio frozen usamos el registro EXISTENTE previo en BD (antes del backfill),
    # no el valor nuevo del proveedor — refleja exactamente el patrón de réplica congelada.
    all_existing_ordered = list(existing_qs)
    if prior:
        all_existing_ordered = [prior] + all_existing_ordered

    def _previous_existing(bucket_str: str) -> Optional[InteractionDetail]:
        target = _parse_chile_bucket(bucket_str)
        prev = None
        for rec in all_existing_ordered:
            if rec.date_time_medition < target:
                prev = rec
            else:
                break
        return prev

    for bucket_str in sorted(bucket_data.keys()):
        vars_in_bucket = bucket_data[bucket_str]
        handler_name = bucket_handlers.get(bucket_str) or detected_provider or "tago"
        payload = _build_register_payload(bucket_str, vars_in_bucket, variables, handler_name)
        existing = existing_by_str.get(bucket_str)
        previous = _previous_existing(bucket_str)
        new_pulses = payload.get("pulses")
        new_logger = payload.get("date_time_last_logger")

        action, reason = decide_bucket_action(
            existing=existing,
            previous=previous,
            new_pulses=new_pulses,
            new_logger_str=new_logger,
            safe=safe,
        )
        by_reason[reason] = by_reason.get(reason, 0) + 1

        hour_entry = {
            "bucket": bucket_str,
            "action": action,
            "reason": reason,
            "before": _snapshot_record(existing),
            "after": payload if action in ("insert", "update") else None,
        }

        if action == "skip":
            omitidos += 1
            hours_report.append(hour_entry)
            if len(sample) < 20:
                sample.append(hour_entry)
            continue

        if dry_run:
            if action == "insert":
                creados += 1
            else:
                actualizados += 1
            hours_report.append(hour_entry)
            if len(sample) < 20:
                sample.append(hour_entry)
            continue

        # Escritura real
        try:
            # Nunca incluir send_dga / n_voucher / return_dga en defaults
            write_fields = {
                k: v for k, v in payload.items()
                if k not in ("send_dga", "n_voucher", "return_dga", "dga_retry_count", "dga_last_retry_at")
            }
            # Persistir datetimes aware en Chile (evita ambigüedad string→UTC)
            write_fields["date_time_medition"] = _parse_chile_bucket(bucket_str)
            if write_fields.get("date_time_last_logger"):
                write_fields["date_time_last_logger"] = _parse_chile_bucket(
                    write_fields["date_time_last_logger"]
                )

            if action == "insert":
                obj = InteractionDetail.objects.create(
                    catchment_point_id=point_id,
                    **write_fields,
                )
                creados += 1
                existing_by_str[bucket_str] = obj
            else:
                obj = existing
                assert obj is not None
                # Preservar send_dga / n_voucher explícitamente
                preserved_send_dga = obj.send_dga
                preserved_voucher = obj.n_voucher
                for field, value in write_fields.items():
                    setattr(obj, field, value)
                obj.send_dga = preserved_send_dga
                obj.n_voucher = preserved_voucher
                obj.save()
                actualizados += 1
                existing_by_str[bucket_str] = obj

            medition_dt = obj.date_time_medition
            changed_ids.add(obj.id)
            hour_entry["interaction_detail_id"] = obj.id
            hours_report.append(hour_entry)
            if len(sample) < 20:
                sample.append(hour_entry)

            logger.info(
                "[BACKFILL] punto=%s bucket=%s action=%s reason=%s id=%s",
                point_id, bucket_str, action, reason, obj.id,
            )
        except Exception as e:
            logger.error("[BACKFILL] Error guardando bucket %s punto %s: %s", bucket_str, point_id, e)
            errores += 1
            fetch_errors.append(str(e))
            hour_entry["action"] = "error"
            hour_entry["error"] = str(e)
            hours_report.append(hour_entry)

    processing_result: Dict[str, Any] = {}
    if not dry_run and changed_ids:
        # Recalc limitado: desde la primera hora tocada hasta fin de rango,
        # pero solo GUARDA sobre las mediciones cambiadas (no toca DGA ni skips).
        changed_qs = InteractionDetail.objects.filter(id__in=changed_ids)
        first_changed = changed_qs.order_by("date_time_medition").values_list(
            "date_time_medition", flat=True
        ).first()
        logger.info(
            "[BACKFILL] punto=%s procesamiento limitado desde %s (%s horas tocadas)",
            point_id, first_changed, len(changed_ids),
        )
        processing_result = process_backfill_range(
            point,
            first_changed,
            end_dt,
            only_ids=changed_ids,
        )

    logger.info(
        "[BACKFILL] punto=%s fin created=%s updated=%s skipped=%s failed=%s by_reason=%s dry_run=%s",
        point_id, creados, actualizados, omitidos, errores, by_reason, dry_run,
    )

    return {
        "success": True,
        "point_id": point_id,
        "provider": detected_provider,
        "range": f"{start_dt.strftime('%Y-%m-%dT%H:%M:%S')} → {end_dt.strftime('%Y-%m-%dT%H:%M:%S')}",
        "dry_run": dry_run,
        "safe": safe,
        "mode": "dry-run" if dry_run else "applied",
        "records_created": creados,
        "records_updated": actualizados,
        "records_skipped": omitidos,
        "records_failed": errores,
        "by_reason": by_reason,
        "processing": processing_result,
        "fetch_errors": fetch_errors,
        "hours": hours_report,
        "sample": sample,
        "dga_note": (
            "send_dga y n_voucher nunca se modifican; no se encola envío a DGA. "
            "Filas con comprobante DGA se omiten (reason=dga_voucher)."
        ),
    }
