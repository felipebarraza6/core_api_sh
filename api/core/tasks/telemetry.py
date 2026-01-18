"""
Celery Tasks for Telemetry Data Collection (V3 UNIFIED)
REEMPLAZA: twin.py, twin_f1.py, twin_f5.py, twin_f10.py, nettra.py, novus.py

Este módulo unifica TODA la ingesta de telemetría:
- Maneja todas las frecuencias (1, 5, 10, 60 min) con UN SOLO código
- Soporta todos los proveedores (TWIN, NETTRA, NOVUS) dinámicamente
- Procesamiento paralelo por batches
- Retry inteligente con backoff exponencial
- Redis para deduplicación y buffer
"""

import logging
import time
from datetime import datetime
from celery import shared_task, group
from django.db import transaction
import pytz

from api.core.models import CatchmentPoint, TelemetryRecord
from api.telemetry.ingestion.controllers.unified_processing import (
    save_telemetry_data,
    process_variable_safely,
    determine_dga_send
)
from api.core.cache.telemetry_cache import TelemetryCache

# GETTERS UNIFICADOS - Soportan todos los proveedores
from api.telemetry.ingestion.getters.tago import get_data_tago
from api.telemetry.ingestion.getters.tdata import get_data_tdata
from api.telemetry.ingestion.getters.thingsio import get_data_thethings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def collect_telemetry(self, frequency_minutes):
    """
    TASK PRINCIPAL DE TELEMETRÍA (Reemplaza 4 cronjobs)

    Llamado por Celery Beat cada N minutos según frecuencia:
    - frequency_minutes="1"  → Cada minuto
    - frequency_minutes="5"  → Cada 5 minutos
    - frequency_minutes="60" → Cada hora

    Procesa puntos en batches paralelos para máximo rendimiento.
    """
    start_time = time.time()

    try:
        logger.info(f"🚀 [TELEMETRY] Starting collection for {frequency_minutes}min frequency")

        # Obtener puntos con telemetría activa para esta frecuencia
        points = CatchmentPoint.objects.filter(
            data_config_profiles__is_telemetry=True,
            frecuency=str(frequency_minutes)
        ).distinct()

        point_count = points.count()

        if point_count == 0:
            logger.info(f"ℹ️  [TELEMETRY] No points configured for {frequency_minutes}min frequency")
            return {
                'status': 'completed',
                'points_processed': 0,
                'frequency': frequency_minutes,
                'duration_seconds': round(time.time() - start_time, 2)
            }

        # Procesar en batches paralelos (20 puntos por batch)
        batch_size = 20
        point_ids = list(points.values_list('id', flat=True))

        batch_tasks = []
        for i in range(0, len(point_ids), batch_size):
            batch_point_ids = point_ids[i:i + batch_size]
            batch_tasks.append(
                process_telemetry_batch.s(batch_point_ids, frequency_minutes)
            )

        # Ejecutar batches en paralelo
        job = group(batch_tasks)
        job.apply_async()

        logger.info(
            f"✅ [TELEMETRY] Dispatched {point_count} points in {len(batch_tasks)} batches "
            f"({frequency_minutes}min frequency) - {round(time.time() - start_time, 2)}s"
        )

        return {
            'status': 'dispatched',
            'points_count': point_count,
            'frequency': frequency_minutes,
            'batches': len(batch_tasks),
            'duration_seconds': round(time.time() - start_time, 2)
        }

    except Exception as exc:
        logger.error(f"❌ [TELEMETRY] Collection failed for {frequency_minutes}min: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=2)
def process_telemetry_batch(self, point_ids, frequency_minutes):
    """
    Procesa un batch de puntos en paralelo.
    Cada punto se procesa con la lógica unificada de V3.
    """
    processed = 0
    errors = 0
    start_time = time.time()

    for point_id in point_ids:
        try:
            success = process_single_point_unified(point_id, frequency_minutes)
            if success:
                processed += 1
            else:
                errors += 1

        except Exception as exc:
            logger.error(f"❌ [TELEMETRY] Failed to process point {point_id}: {exc}")
            errors += 1

    duration = round(time.time() - start_time, 2)
    logger.info(
        f"✅ [BATCH] Processed {processed}/{len(point_ids)} points "
        f"({errors} errors) in {duration}s"
    )

    return {
        'processed': processed,
        'errors': errors,
        'batch_size': len(point_ids),
        'duration_seconds': duration
    }


def process_single_point_unified(point_id, frequency_minutes):
    """
    LÓGICA UNIFICADA DE PROCESAMIENTO (Reemplaza get_data_twin)

    Esta función consolida TODA la lógica de:
    - twin.py / twin_f1.py / twin_f5.py / twin_f10.py
    - nettra.py / nettra_f5.py
    - novus.py

    La diferencia entre proveedores está en el campo "service" de cada variable.
    La diferencia entre frecuencias está en el filtro, NO en el código.
    """
    try:
        from api.core.serializers import CatchmentPointSerializerDetailCron

        point = CatchmentPoint.objects.get(id=point_id)
        serializer = CatchmentPointSerializerDetailCron(point)
        data = serializer.data

        profile_data_config = data.get("profile_data_config", {})
        variables = profile_data_config.get("scheme", {}).get("variables", [])
        token = profile_data_config.get("token_service")

        if not variables or not token:
            logger.warning(f"⚠️  [POINT {point_id}] Missing variables or token")
            return False

        # Ejecutar ingesta con lógica V3
        success = ingest_telemetry_data(variables, token, data, frequency_minutes)

        if success:
            # Invalidar cache Redis para este punto
            TelemetryCache.invalidate_point_cache(point_id)
            logger.debug(f"✅ [POINT {point_id}] Telemetry ingested successfully")
            return True
        else:
            logger.warning(f"⚠️  [POINT {point_id}] Ingestion returned no data")
            return False

    except CatchmentPoint.DoesNotExist:
        logger.error(f"❌ [POINT {point_id}] Point not found")
        return False
    except Exception as exc:
        logger.error(f"❌ [POINT {point_id}] Processing error: {exc}")
        return False


def ingest_telemetry_data(variables, token, point_catchment, frequency_minutes):
    """
    LÓGICA UNIFICADA DE INGESTA (Corazón del sistema)

    Esta función reemplaza el código duplicado en todos los scripts legacy.
    Maneja dinámicamente:
    - Múltiples variables por punto
    - Múltiples proveedores (TWIN, NETTRA, NOVUS)
    - Retry con backoff exponencial
    - Formateo de timestamp según frecuencia
    - Cálculo de send_dga
    """
    chile = pytz.timezone("America/Santiago")

    # Formateo de timestamp según frecuencia
    if frequency_minutes == "60":
        timestamp_format = "%Y-%m-%dT%H:00:00"
    else:
        timestamp_format = "%Y-%m-%dT%H:%M:00"

    created_register = {
        "date_time_medition": datetime.now(chile).strftime(timestamp_format)
    }

    date_time_last_logger_total = None
    variable_details = []
    has_valid_data = False

    for variable in variables:
        var_str = variable.get("str_variable")
        type_var = variable.get("type_variable")
        service = variable.get("service")
        token_service = variable.get("token_service") or token

        # CAUDAL_PROMEDIO se calcula dinámicamente, no se pide a API
        if type_var == "CAUDAL_PROMEDIO":
            continue

        # Obtener data según proveedor con retry inteligente
        data = get_data_with_retry(service, token_service, var_str)

        # Manejo de datos nulos
        if data is None:
            data = {"value": 0, "date_time": None}
        else:
            has_valid_data = True

        # Procesamiento unificado de la variable
        date_time_last_logger_total, created_register = process_variable_safely(
            variable, data, point_catchment, created_register, date_time_last_logger_total
        )

        # Guardar detalles para metadata
        variable_details.append({
            "name": var_str,
            "type": type_var,
            "service": service,
            "timestamp": data.get("date_time")
        })

    # No guardar si no hay datos válidos
    if not has_valid_data:
        return False

    # Determinar si debe enviar a DGA
    created_register["send_dga"] = determine_dga_send(point_catchment, chile)
    created_register["variable_details"] = variable_details

    # GUARDADO FINAL EN V3 (TelemetryRecord)
    save_telemetry_data(point_catchment["id"], created_register)
    return True


def get_data_with_retry(service, token, variable, max_retries=3, backoff_factor=2):
    """
    Retry inteligente con backoff exponencial.

    Mapea el servicio al getter correcto:
    - TWIN   → TData API
    - NETTRA → TheThings API
    - NOVUS  → Tago API
    """
    # Selección de getter según proveedor
    getter_map = {
        "TWIN": get_data_tdata,
        "NETTRA": get_data_thethings,
        "NOVUS": get_data_tago,
    }

    getter_func = getter_map.get(service, get_data_tdata)  # Default: TWIN

    for attempt in range(max_retries):
        try:
            data = getter_func(token, variable)
            if data and data.get("value") is not None:
                return data
        except Exception as exc:
            if attempt == max_retries - 1:
                logger.error(
                    f"❌ [RETRY] Failed after {max_retries} attempts for {service}/{variable}: {exc}"
                )
                return None
            time.sleep(backoff_factor ** attempt)

    return None
