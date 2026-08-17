"""
Runner unificado de telemetría — EJECUTAR EN PARALELO A LOS 7 LEGACY.

Este archivo reemplaza progresivamente a twin.py, twin_f1.py, twin_f5.py,
twin_f10.py, nettra.py, nettra_f5.py y novus.py.

Principios:
- Corre por frecuencia (1, 5, 10, 60 min), no por marca.
- Usa get_data_universal para soportar cualquier proveedor (tdata, thethings, tago, generic_json).
- Lee reglas configurables desde la base de datos (nivel_offset, store_average_flow, etc.).
- Mantiene requests.Session() persistente para reutilizar conexiones TCP.
- Modo dry_run para shadow mode (comparar sin guardar).
"""

import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from django.utils import timezone

from django.db.models import Q

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail
from api.core.serializers import CatchmentPointSerializerDetailCron

from api.cronjobs.telemetry.controllers.unified_processing import (
    calculate_days_not_connection,
    get_data_with_retry,
    log_variable_processing,
    process_variable_safely,
    validate_frequency,
)
from api.cronjobs.telemetry.getters.universal import get_data_universal
from api.cronjobs.utils.logging_config import telemetry_logger

# Session HTTP persistente: reutiliza conexiones TCP y reduce overhead.
_HTTP_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        _HTTP_SESSION = requests.Session()
    return _HTTP_SESSION


def run_novus_60():
    """Wrapper para crontab: ejecuta Novus frecuencia 60."""
    run(frequency="60", point_type="novus")


def run_nettra_60():
    """Wrapper para crontab: ejecuta Nettra frecuencia 60."""
    run(frequency="60", point_type="thethings")


def run_twin_60():
    """Wrapper para crontab: ejecuta Twin/TDATA frecuencia 60."""
    run(frequency="60", point_type="tdata")


def run_twin_5():
    """Wrapper para crontab: ejecuta Twin/TDATA frecuencia 5."""
    run(frequency="5", point_type="tdata")


def run_twin_10():
    """Wrapper para crontab: ejecuta Twin/TDATA frecuencia 10."""
    run(frequency="10", point_type="tdata")


def run_twin_1():
    """Wrapper para crontab: ejecuta Twin/TDATA frecuencia 1."""
    run(frequency="1", point_type="tdata")


def run(frequency: str, dry_run: bool = False, point_id: Optional[int] = None, point_type: Optional[str] = None):
    """
    Punto de entrada del runner unificado.

    Args:
        frequency: "1", "5", "10" o "60".
        dry_run: Si True, NO escribe en BD (útil para shadow mode).
        point_id: Si se pasa, solo procesa este punto.
        point_type: Filtra por tipo de punto (tdata, thethings, novus).
    """
    chile = timezone.get_current_timezone()
    now = datetime.now(chile)

    # Buscar todos los puntos telemetría con la frecuencia dada
    # Excluir puntos de formulario (entry_by_form) para evitar procesar puntos manuales
    # Excluir puntos TheThings.io que reciben datos vía MQTT/webhook
    puntos_qs = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True,
        frecuency=frequency,
    ).exclude(
        ikolu_profiles__entry_by_form=True,
    ).exclude(
        data_config_profiles__disable_thethings_polling=True,
    )
    if point_id:
        puntos_qs = puntos_qs.filter(id=point_id)
    if point_type:
        # ✅ NUEVO: Filtrar por telemetry_provider (configurable)
        # Fallback a booleanos legacy para compatibilidad
        flag = {"tdata": "is_tdata", "thethings": "is_thethings", "novus": "is_novus"}.get(point_type)
        if flag:
            puntos_qs = puntos_qs.filter(
                Q(telemetry_provider__handler_name=point_type) | Q(**{flag: True})
            )

    serializer = CatchmentPointSerializerDetailCron(puntos_qs, many=True)

    processed = 0
    errors = 0
    skipped_lock = 0

    # Health check de Redis antes del loop: si está caído, todos los locks fallan
    # y cada punto loguea "bloqueado por otro proceso" (misleading). Mejor skip uma vez.
    try:
        from django.core.cache import cache
        cache.set("_smarthydro:healthcheck", 1, 10)
    except Exception as e:
        telemetry_logger.critical(
            f"[UNIFIED] Redis NO disponible ({e}). "
            f"Todos los puntos serán omitidos en este ciclo. "
            f"La ingesta se reanudará cuando Redis recupere."
        )
        telemetry_logger.info(
            f"[UNIFIED] Frecuencia={frequency} | Procesados=0 | Errores=0 | "
            f"Omitidos_redis={len(serializer.data)} | dry_run={dry_run}"
        )
        return

    # Calcular TTL del lock dinámicamente según frecuencia:
    # nunca debe expirar antes del siguiente ciclo del mismo punto.
    try:
        freq_minutes = int(frequency)
    except (ValueError, TypeError):
        freq_minutes = 60
    lock_timeout = max(300, freq_minutes * 60 + 60)  # mínimo 5 minutos

    for point_data in serializer.data:
        point_id = point_data.get("id")

        # Adquirir lock por punto para prevenir race condition en total_m3
        from api.cronjobs.telemetry.utils.locks import acquire_point_lock, release_point_lock
        if not acquire_point_lock(point_id, timeout=lock_timeout):
            skipped_lock += 1
            telemetry_logger.debug(
                f"[UNIFIED] Punto {point_id} omitido (lock no adquirido)."
            )
            continue

        try:
            _process_point(point_data, now, frequency, dry_run)
            processed += 1
        except Exception as e:
            errors += 1
            telemetry_logger.error(
                f"[UNIFIED] Error procesando punto {point_id}: {e}",
                exc_info=True,
            )
        finally:
            try:
                release_point_lock(point_id)
            except Exception:
                pass  # Ya logueado en locks.py; no enmascarar excepción original

    telemetry_logger.info(
        f"[UNIFIED] Frecuencia={frequency} | Procesados={processed} | Errores={errors} | "
        f"Omitidos_lock={skipped_lock} | dry_run={dry_run}"
    )


def _process_point(
    point_catchment: Dict[str, Any],
    now: datetime,
    frequency: str,
    dry_run: bool,
):
    """Procesa un punto completo: obtiene datos, calcula, guarda."""
    point_id = point_catchment["id"]
    profile = point_catchment.get("profile_data_config", {})

    # Token del punto (fallback legacy)
    point_token = profile.get("token_service") or ""

    # Formato de timestamp según frecuencia
    if frequency == "60":
        medition_str = now.strftime("%Y-%m-%dT%H:00:00")
    else:
        medition_str = now.strftime("%Y-%m-%dT%H:%M:00")

    created_register: Dict[str, Any] = {
        "date_time_medition": medition_str,
    }

    # Reglas configurables del profile
    replicate_on_missing = bool(profile.get("replicate_on_missing", False))
    use_transaction = bool(profile.get("use_transaction_atomic", True))

    variables = profile.get("scheme", {}).get("variables", [])
    if not variables:
        telemetry_logger.warning(f"[UNIFIED] Punto {point_id} sin variables")
        return

    date_time_last_logger_total: Optional[str] = None
    max_days_not_conection = 0
    best_date_time_last_logger: Optional[datetime] = None
    variable_details: list = []

    for variable in variables:
        data = None

        if variable.get("type_variable") != "CAUDAL_PROMEDIO":
            token = variable.get("token_service") or point_token
            provider = variable.get("provider")

            data = get_data_with_retry(
                get_data_universal,
                provider,
                token,
                variable.get("str_variable"),
            )

        # Detectar fallo de getter: si date_time es None y value es 0,
        # es casi seguro un fallo de API/sensor, no una medición real.
        # Para TOTALIZADO con historial previo, marcar como error de ingesta.
        if data is None:
            if variable.get("type_variable") == "TOTALIZADO":
                data = {"value": 0, "date_time": None}
            else:
                data = {"value": 0.00, "date_time": None}

        if not data.get("value") and data.get("value") != 0:
            data["value"] = 0

        # Heurística de detección de fallo de getter:
        # date_time=None indica que el getter no pudo contactar al sensor/API.
        # value=0 en este contexto NO es una medición real.
        if data.get("date_time") is None and data.get("value") == 0:
            # Solo marcar is_error a nivel de registro si falla TOTALIZADO,
            # que es la variable crítica. Si falla caudal o nivel, el registro
            # sigue siendo válido porque el totalizado llegó bien.
            if variable.get("type_variable") == "TOTALIZADO":
                telemetry_logger.warning(
                    f"[UNIFIED] Punto {point_id} - {variable.get('str_variable')}: "
                    f"Getter retornó value=0 sin timestamp. Probable fallo de ingesta. "
                    f"Marcando is_error=True."
                )
                from api.cronjobs.telemetry.utils.audit import emit_system_event
                emit_system_event(
                    event_type="API_ERROR",
                    point_id=point_id,
                    title="Getter retornó valor sin timestamp",
                    message=f"Variable {variable.get('str_variable')}: getter retornó value=0 sin timestamp. Probable fallo de ingesta.",
                    severity="CRITICAL",
                    extra_data={
                        "decision": "MARCAR_ERROR",
                        "reason": "El getter de la API de telemetría no pudo obtener un timestamp válido junto con el valor. Para variables TOTALIZADO esto indica una falla de comunicación con el sensor o la plataforma. Se marca el registro como error para no usarlo como baseline.",
                        "actual_value": 0,
                        "expected_range": [1, None],
                        "variable": variable.get('str_variable'),
                        "value": 0,
                        "date_time": None,
                        "is_error": True,
                        "source": "api.cronjobs.telemetry.telemetry_unified:_process_point",
                    },
                )
                created_register["is_error"] = True
            else:
                telemetry_logger.warning(
                    f"[UNIFIED] Punto {point_id} - {variable.get('str_variable')}: "
                    f"Getter retornó value=0 sin timestamp. Variable secundaria fallida; "
                    f"registro sigue válido."
                )

        # Procesar variable usando unified_processing (ahora configurable)
        # Pasar medition_str para garantizar coherencia de zonas horarias
        # en total_day, total_hour y anti-salto.
        date_time_last_logger_total, created_register = process_variable_safely(
            variable=variable,
            data=data,
            point_catchment=point_catchment,
            created_register=created_register,
            date_time_last_logger_total=date_time_last_logger_total,
            medition_str=medition_str,
        )

        # Tracking de días sin conexión (mismo patrón que legacy)
        days_not_conection = created_register.get("days_not_conection", 0)
        if days_not_conection > max_days_not_conection:
            max_days_not_conection = days_not_conection

        if created_register.get("date_time_last_logger"):
            try:
                dt_lg = datetime.strptime(created_register["date_time_last_logger"], "%Y-%m-%dT%H:%M:%S")
                if best_date_time_last_logger is None or dt_lg > best_date_time_last_logger:
                    best_date_time_last_logger = dt_lg
            except Exception as e:
                telemetry_logger.debug(f"[UNIFIED] Fecha logger inválida para punto {point_id}: {e}")

        # Guardar valor crudo en variable_values (esquema dinámico)
        var_id = variable.get("id")
        if var_id is not None:
            if "variable_values" not in created_register:
                created_register["variable_values"] = {}
            created_register["variable_values"][str(var_id)] = data.get("value")

        # Detalle para variable_details (compatibilidad con legacy)
        # ✅ FIX: success refleja si el getter realmente funcionó (date_time no es None)
        getter_succeeded = data.get("date_time") is not None
        variable_details.append({
            "str_variable": variable.get("str_variable"),
            "type_variable": variable.get("type_variable"),
            "value": data.get("value"),
            "success": getter_succeeded,
        })

    # Replicar último registro si no hay datos y está configurado (Nettra legacy)
    if replicate_on_missing and best_date_time_last_logger is None:
        _replicate_last_record(point_id, created_register, now)

    created_register["variable_details"] = variable_details
    created_register["is_partial"] = False

    # Determinar si enviar a DGA
    try:
        dga_config = DgaDataConfigCatchment.objects.get(point_catchment_id=point_id)
        record_time = datetime.strptime(medition_str, "%Y-%m-%dT%H:%M:%S" if frequency != "60" else "%Y-%m-%dT%H:00:00")
        created_register["send_dga"] = dga_config.send_dga and validate_frequency(point_catchment, record_time, frequency)
    except DgaDataConfigCatchment.DoesNotExist:
        # Punto sin config DGA: normal, no loguear para evitar ruido
        created_register["send_dga"] = False
    except Exception as e:
        telemetry_logger.warning(f"[UNIFIED] Error DGA config punto {point_id}: {e}")
        created_register["send_dga"] = False

    # Guardar en BD (o loguear si dry_run)
    if dry_run:
        telemetry_logger.info(
            f"[DRY-RUN] Punto {point_id} | total={created_register.get('total')} | "
            f"flow={created_register.get('flow')} | nivel={created_register.get('nivel')} | "
            f"send_dga={created_register.get('send_dga')}"
        )
        return

    _save_to_db(point_id, medition_str, created_register, use_transaction)


def _replicate_last_record(point_id: int, created_register: Dict[str, Any], now: datetime):
    """Replica el último registro válido cuando no hay datos nuevos (legacy Nettra)."""
    try:
        last_valid = InteractionDetail.objects.filter(
            catchment_point_id=point_id,
        ).exclude(date_time_last_logger__isnull=True).exclude(is_error=True).order_by("-created").first()

        if last_valid:
            created_register["total"] = last_valid.total
            created_register["total_diff"] = last_valid.total_diff
            created_register["total_today_diff"] = last_valid.total_today_diff
            created_register["flow"] = last_valid.flow
            created_register["nivel"] = last_valid.nivel
            created_register["water_table"] = last_valid.water_table
            created_register["pulses"] = last_valid.pulses
            created_register["date_time_last_logger"] = (
                last_valid.date_time_last_logger.strftime("%Y-%m-%dT%H:%M:%S")
                if last_valid.date_time_last_logger
                else None
            )
            created_register["days_not_conection"] = 9999
            created_register["is_partial"] = False
            created_register["variable_details"] = []
            telemetry_logger.info(f"[UNIFIED] Punto {point_id}: replicado último registro válido")
        else:
            created_register["flow"] = 0.00
            created_register["total"] = "0"
            created_register["total_diff"] = 0
            created_register["total_today_diff"] = 0
            created_register["nivel"] = 0.00
            created_register["water_table"] = 0.00
            created_register["pulses"] = 0
            created_register["date_time_last_logger"] = None
            created_register["days_not_conection"] = 9999
            created_register["is_partial"] = False
            created_register["variable_details"] = []
    except Exception as e:
        telemetry_logger.warning(f"[UNIFIED] Error replicando último registro para punto {point_id}: {e}")


def _save_to_db(
    point_id: int,
    medition_str: str,
    created_register: Dict[str, Any],
    use_transaction: bool,
):
    """Guarda el registro en InteractionDetail."""
    try:
        if use_transaction:
            from django.db import transaction as db_transaction
            with db_transaction.atomic():
                InteractionDetail.objects.update_or_create(
                    catchment_point_id=point_id,
                    date_time_medition=medition_str,
                    defaults=created_register,
                )
        else:
            InteractionDetail.objects.update_or_create(
                catchment_point_id=point_id,
                date_time_medition=medition_str,
                defaults=created_register,
            )
        telemetry_logger.debug(f"[UNIFIED] Punto {point_id} guardado OK")
    except Exception as e:
        telemetry_logger.error(f"[UNIFIED] Error guardando punto {point_id}: {e}", exc_info=True)
