#!/usr/bin/env python3
"""
BACKFILL — Reconstrucción de date_time_last_logger para CMPC S3
===============================================================

Problema: El punto CMPC S3 tenía un bug donde procesamiento de NIVEL/CAUDAL
sobrescribía date_time_last_logger con None, dejando registros sin fecha de logger.

Este script:
1. Identifica el punto CMPC S3 (title='S3', proyecto CMPC)
2. Busca registros de los últimos N días con date_time_last_logger IS NULL
3. Consulta histórico TDATA para obtener timestamps reales del logger
4. Actualiza los registros afectados con la fecha real o fallback a medición

USO (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/backfill_logger_date_cmpc_s3.py

USO (aplicar):
    docker exec -u root -w /app -e FORCE_BACKFILL=1 django_api_secure python scripts/backfill_logger_date_cmpc_s3.py

USO (rango personalizado, ej. últimos 14 días):
    docker exec -u root -w /app -e FORCE_BACKFILL=1 -e DAYS=14 django_api_secure python scripts/backfill_logger_date_cmpc_s3.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz
from django.db import transaction
from api.core.models import CatchmentPoint, InteractionDetail, Variable, SchemesCatchment
from api.cronjobs.telemetry.getters.tdata import get_data_tdata_history

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

FORCE = os.environ.get("FORCE_BACKFILL", "0") == "1"
DAYS = int(os.environ.get("DAYS", "7"))
CHILE_TZ = pytz.timezone("America/Santiago")


def log(msg):
    print(msg, flush=True)


def find_cmpc_s3_point():
    """Buscar punto S3 del proyecto CMPC."""
    point = CatchmentPoint.objects.select_related("project__client").filter(
        title__iexact="S3",
        project__client__name__iexact="CMPC",
    ).first()
    if not point:
        # Fallback: buscar por title conteniendo S3 y cliente CMPC
        point = CatchmentPoint.objects.select_related("project__client").filter(
            title__icontains="S3",
            project__client__name__iexact="CMPC",
        ).first()
    return point


def get_point_config(point):
    """Obtener token y variables del punto."""
    profile = point.data_config_profiles.filter(is_telemetry=True).first()
    if not profile:
        return None, None, None

    scheme = SchemesCatchment.objects.filter(points_catchment=point).first()
    if not scheme:
        return None, None, None

    variables = list(Variable.objects.filter(scheme_catchment=scheme).select_related("provider"))
    point_token = profile.token_service or ""
    return profile, variables, point_token


def fetch_tdata_timestamps(provider, token_service, str_variable, start_dt, end_dt):
    """
    Consulta histórico TDATA y devuelve dict: bucket_str -> timestamp_str
    El bucket se trunca a hora en punto (frecuencia 60).
    """
    history = get_data_tdata_history(
        provider=provider,
        token_service=token_service,
        str_variable=str_variable,
        start_dt=start_dt.astimezone(timezone.utc).replace(tzinfo=None),
        end_dt=end_dt.astimezone(timezone.utc).replace(tzinfo=None),
        limit=10000,
    )

    bucket_map = {}
    for item in history:
        item_dt = datetime.strptime(item["date_time"], "%Y-%m-%dT%H:%M:%S")
        item_dt = pytz.utc.localize(item_dt).astimezone(CHILE_TZ)
        bucket = item_dt.replace(minute=0, second=0, microsecond=0)
        bucket_str = bucket.strftime("%Y-%m-%dT%H:%M:%S")
        # Guardar el timestamp más reciente por bucket (si hay múltiples)
        if bucket_str not in bucket_map:
            bucket_map[bucket_str] = item["date_time"]
        else:
            existing_dt = datetime.strptime(bucket_map[bucket_str], "%Y-%m-%dT%H:%M:%S")
            new_dt = datetime.strptime(item["date_time"], "%Y-%m-%dT%H:%M:%S")
            if new_dt > existing_dt:
                bucket_map[bucket_str] = item["date_time"]

    return bucket_map


def main():
    log("=" * 70)
    log("BACKFILL date_time_last_logger — CMPC S3")
    log("=" * 70)
    log(f"Rango: últimos {DAYS} días")
    log(f"Modo: {'APLICAR CAMBIOS REALES' if FORCE else 'DRY-RUN (solo simula)'}")
    log("")

    # 1. Encontrar punto
    point = find_cmpc_s3_point()
    if not point:
        log("❌ No se encontró punto CMPC S3. Verifica que exista un punto con title='S3' y cliente='CMPC'.")
        sys.exit(1)

    log(f"📍 Punto encontrado: ID={point.id} | Title='{point.title}' | Project='{point.project.name}' | Client='{point.project.client.name}'")

    # 2. Obtener configuración
    profile, variables, point_token = get_point_config(point)
    if not profile:
        log("❌ Punto sin perfil de telemetría configurado.")
        sys.exit(1)
    if not variables:
        log("❌ Punto sin variables configuradas.")
        sys.exit(1)
    if not point_token:
        log("❌ Punto sin token de servicio.")
        sys.exit(1)

    # 3. Determinar variable primaria (TOTALIZADO preferida)
    var_by_type = {v.type_variable: v for v in variables}
    primary_var = var_by_type.get("TOTALIZADO") or var_by_type.get("CAUDAL") or var_by_type.get("NIVEL")
    if not primary_var:
        log("❌ No se encontró variable TOTALIZADO, CAUDAL ni NIVEL.")
        sys.exit(1)

    provider = primary_var.provider
    str_variable = primary_var.str_variable
    log(f"🔧 Variable primaria: {primary_var.type_variable} ('{str_variable}') | Token: {point_token[:8]}...")

    # 4. Calcular rango
    now = datetime.now(CHILE_TZ)
    end_dt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    start_dt = end_dt - timedelta(days=DAYS)
    start_dt = start_dt.replace(minute=0, second=0, microsecond=0)

    log(f"📅 Rango consulta: {start_dt.strftime('%Y-%m-%dT%H:%M:%S')} → {end_dt.strftime('%Y-%m-%dT%H:%M:%S')}")

    # 5. Obtener timestamps de TDATA
    log("⏳ Consultando histórico TDATA...")
    try:
        tdata_map = fetch_tdata_timestamps(provider, point_token, str_variable, start_dt, end_dt)
        log(f"✅ Timestamps recibidos de TDATA: {len(tdata_map)} registros")
    except Exception as e:
        log(f"⚠️ Error consultando TDATA: {e}")
        log("   Continuando con fallback a date_time_medition para todos los registros.")
        tdata_map = {}

    # 6. Buscar registros afectados en BD
    affected = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=start_dt,
        date_time_medition__lt=end_dt,
        date_time_last_logger__isnull=True,
    ).order_by("date_time_medition")

    total_affected = affected.count()
    if total_affected == 0:
        log("✅ No hay registros afectados (date_time_last_logger IS NULL) en el rango.")
        sys.exit(0)

    log(f"📝 Registros afectados en BD: {total_affected}")

    # 7. Procesar actualizaciones
    updated = 0
    updated_with_tdata = 0
    updated_with_fallback = 0
    errors = 0

    for reg in affected:
        medition_str = reg.date_time_medition.strftime("%Y-%m-%dT%H:%M:%S")

        # Intentar match con TDATA (truncado a hora)
        bucket_str = reg.date_time_medition.strftime("%Y-%m-%dT%H:00:00")
        new_logger_date = tdata_map.get(bucket_str)

        if new_logger_date:
            source = "TDATA"
            updated_with_tdata += 1
        else:
            # Fallback: usar date_time_medition (el totalizado funcionó, así que el logger estaba vivo)
            # ✅ FIX TZ: No usar string, asignar el datetime object directamente para evitar
            # que AwareDateTimeField reinterprete una hora UTC como hora Chile.
            new_logger_date = reg.date_time_medition
            source = "fallback (date_time_medition)"
            updated_with_fallback += 1

        if FORCE:
            try:
                # Calcular days_not_conection
                try:
                    dt_med = reg.date_time_medition
                    dt_log = new_logger_date if isinstance(new_logger_date, datetime) else datetime.strptime(new_logger_date, "%Y-%m-%dT%H:%M:%S")
                    if dt_med.tzinfo and not dt_log.tzinfo:
                        dt_log = CHILE_TZ.localize(dt_log)
                    days = (dt_med - dt_log).days
                    days_not_conection = max(0, days)
                except Exception:
                    days_not_conection = 0

                reg.date_time_last_logger = new_logger_date
                reg.days_not_conection = days_not_conection
                reg.save(update_fields=["date_time_last_logger", "days_not_conection"])
                updated += 1
            except Exception as e:
                log(f"   ❌ Error actualizando {medition_str}: {e}")
                errors += 1
        else:
            display_dt = new_logger_date.strftime("%Y-%m-%dT%H:%M:%S") if isinstance(new_logger_date, datetime) else new_logger_date
            log(f"   [DRY-RUN] {medition_str} → date_time_last_logger={display_dt} (fuente: {source})")
            updated += 1

    log("")
    log("=" * 70)
    log("RESUMEN")
    log("=" * 70)
    log(f"Registros afectados:    {total_affected}")
    if FORCE:
        log(f"Actualizados con TDATA: {updated_with_tdata}")
        log(f"Actualizados fallback:  {updated_with_fallback}")
        log(f"Errores:                {errors}")
        log("✅ Backfill aplicado.")
    else:
        log(f"Simulados con TDATA:    {updated_with_tdata}")
        log(f"Simulados fallback:     {updated_with_fallback}")
        log("")
        log("⚠️  Esto fue DRY-RUN. Para aplicar cambios reales:")
        log(f"   docker exec -u root -w /app -e FORCE_BACKFILL=1 django_api_secure python scripts/backfill_logger_date_cmpc_s3.py")


if __name__ == "__main__":
    main()
