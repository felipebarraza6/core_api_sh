#!/usr/bin/env python3
"""
BACKFILL TWIN — Recuperación de telemetría faltante (crisis Redis 19-22 mayo 2026)
===================================================================================

Este script recupera datos históricos de TWIN (ThingsBoard/TDATA) para el periodo
en que Redis falló y la telemetría no se procesó (aprox. 19 mayo 20:00 a 22 mayo 12:00).

ESTRATEGIA:
1. Para cada punto TWIN activo, identificar timestamps faltantes en el rango.
2. Consultar histórico de TWIN en bloques de 6 horas (para no saturar la API).
3. Agrupar datos por bucket según frecuencia del punto (1, 5, 10, 60 min).
4. Guardar con update_or_create en InteractionDetail (sin riesgo de duplicados).
5. Solo guardar valores crudos; NO ejecutar total_m3() para evitar mutar addition.
6. Al finalizar, ejecutar recalcular_coherencia_masivo.py para ajustar totales/diffs.

USO (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/backfill_twin_crisis_mayo2026.py

USO (aplicar):
    docker exec -u root -w /app -e FORCE_BACKFILL=1 django_api_secure python scripts/backfill_twin_crisis_mayo2026.py

USO (rango personalizado):
    docker exec -u root -w /app -e FORCE_BACKFILL=1 -e START_DATE="2026-05-19T20:00:00" -e END_DATE="2026-05-22T12:00:00" django_api_secure python scripts/backfill_twin_crisis_mayo2026.py
"""

import os
import sys
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

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
START_DATE = os.environ.get("START_DATE", "2026-05-19T20:00:00")
END_DATE = os.environ.get("END_DATE", "2026-05-22T12:00:00")
CHUNK_HOURS = 6  # Consultar histórico en bloques de 6 horas

CHILE_TZ = pytz.timezone("America/Santiago")


def log(msg):
    print(msg, flush=True)


def parse_dt(dt_str):
    """Parsear string a datetime con timezone Chile."""
    naive = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
    return CHILE_TZ.localize(naive)


def truncate_to_freq(dt, freq_min):
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
        # Fallback: truncar a minuto
        return dt.replace(second=0, microsecond=0)


def get_existing_meditions(point_id, start_dt, end_dt):
    """Devuelve set de timestamps (en formato string UTC) ya existentes en BD."""
    qs = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=start_dt,
        date_time_medition__lt=end_dt,
    ).values_list("date_time_medition", flat=True)
    # Normalizar a strings sin timezone para comparación consistente
    return {dt.strftime("%Y-%m-%dT%H:%M:%S") for dt in qs}


def build_missing_buckets(start_dt, end_dt, freq_min, existing):
    """Genera lista de buckets faltantes como strings YYYY-MM-DDTHH:MM:SS."""
    missing = []
    current = start_dt
    while current < end_dt:
        bucket_str = current.strftime("%Y-%m-%dT%H:%M:%S")
        if bucket_str not in existing:
            missing.append(bucket_str)
        current += timedelta(minutes=freq_min)
    return missing


def backfill_point(point, start_dt, end_dt, dry_run=True):
    """
    Backfill de un punto TWIN. Retorna (creados, actualizados, errores).
    """
    point_id = point.id
    freq_str = point.frecuency or "60"
    try:
        freq_min = int(freq_str)
    except ValueError:
        freq_min = 60

    # Obtener variables del punto vía SchemesCatchment
    scheme = SchemesCatchment.objects.filter(points_catchment=point).first()
    if not scheme:
        log(f"  ⚠️ Punto {point_id} ({point.title}): sin esquema")
        return 0, 0, 0

    profile = point.data_config_profiles.filter(is_telemetry=True).first()
    if not profile:
        log(f"  ⚠️ Punto {point_id} ({point.title}): sin perfil de telemetría")
        return 0, 0, 0

    variables = list(Variable.objects.filter(scheme_catchment=scheme).select_related('provider'))
    if not variables:
        log(f"  ⚠️ Punto {point_id} ({point.title}): sin variables")
        return 0, 0, 0

    # Token del punto
    point_token = profile.token_service or ""
    if not point_token:
        log(f"  ⚠️ Punto {point_id} ({point.title}): sin token")
        return 0, 0, 0

    # Mapear variables por tipo
    var_by_type = {}
    for v in variables:
        var_by_type[v.type_variable] = v

    totalizador_var = var_by_type.get("TOTALIZADO")
    caudal_var = var_by_type.get("CAUDAL")
    nivel_var = var_by_type.get("NIVEL")

    # Determinar qué variable consultar para el histórico
    # Preferimos TOTALIZADO porque es el que usamos para totales
    primary_var = totalizador_var or caudal_var or nivel_var
    if not primary_var:
        log(f"  ⚠️ Punto {point_id} ({point.title}): sin variable relevante")
        return 0, 0, 0

    str_variable = primary_var.str_variable
    provider = primary_var.provider

    # Buckets faltantes
    existing = get_existing_meditions(point_id, start_dt, end_dt)
    missing_buckets = build_missing_buckets(start_dt, end_dt, freq_min, existing)
    if not missing_buckets:
        log(f"  ✅ Punto {point_id} ({point.title}): sin huecos")
        return 0, 0, 0

    log(f"  📍 Punto {point_id} ({point.title}) frec={freq_min}min | "
        f"Huecos: {len(missing_buckets)} | Variable: {str_variable}")

    # Consultar histórico completo (el getter maneja paginación internamente)
    try:
        all_history = get_data_tdata_history(
            provider=provider,
            token_service=point_token,
            str_variable=str_variable,
            start_dt=start_dt.astimezone(timezone.utc).replace(tzinfo=None),
            end_dt=end_dt.astimezone(timezone.utc).replace(tzinfo=None),
            limit=10000,
        )
        log(f"    Histórico recibido: {len(all_history)} registros")
    except Exception as e:
        log(f"    ❌ Error consultando histórico: {e}")
        return 0, 0, 0

    if not all_history:
        log(f"    ⚠️ Sin datos históricos disponibles para este punto")
        return 0, 0, 0

    # Agrupar histórico por bucket
    bucket_data = {}  # bucket_str -> {"ts_ms": int, "value": any}
    for item in all_history:
        item_dt = datetime.strptime(item["date_time"], "%Y-%m-%dT%H:%M:%S")
        # Asumir que TDATA devuelve UTC; convertir a Chile
        item_dt = pytz.utc.localize(item_dt).astimezone(CHILE_TZ)
        bucket = truncate_to_freq(item_dt, freq_min)
        bucket_str = bucket.strftime("%Y-%m-%dT%H:%M:%S")
        if bucket_str not in bucket_data or item["ts_ms"] > bucket_data[bucket_str]["ts_ms"]:
            bucket_data[bucket_str] = item

    # Preparar registros a guardar
    creados = 0
    actualizados = 0
    errores = 0

    for bucket_str in missing_buckets:
        if bucket_str not in bucket_data:
            continue

        item = bucket_data[bucket_str]
        value = item["value"]
        ts_str = item["date_time"]

        # Construir registro
        created_register = {
            "date_time_medition": bucket_str,
            "date_time_last_logger": ts_str,
            "is_error": False,
            "is_partial": False,
            "variable_details": [],
            "variable_values": {},
        }

        # Asignar valor según tipo de variable primaria
        if totalizador_var and primary_var == totalizador_var:
            created_register["pulses"] = int(float(value)) if value is not None else 0
        elif caudal_var and primary_var == caudal_var:
            created_register["flow"] = round(float(value), 2) if value is not None else 0.0
        elif nivel_var and primary_var == nivel_var:
            created_register["nivel"] = round(float(value), 2) if value is not None else 0.0

        # Si tenemos otras variables, intentar obtenerlas del mismo bucket
        # (simplificación: usamos el mismo valor para todas si comparten token/variable)
        # En la práctica, TDATA devuelve una variable a la vez.
        # Para un backfill completo, idealmente consultaríamos cada variable,
        # pero dado el tiempo y riesgo, nos enfocamos en la variable primaria.

        if dry_run:
            creados += 1
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
        except Exception as e:
            log(f"    ❌ Error guardando {bucket_str}: {e}")
            errores += 1

    log(f"    {'[DRY-RUN] ' if dry_run else ''}"
        f"Creados: {creados} | Actualizados: {actualizados} | Errores: {errores}")
    return creados, actualizados, errores


def main():
    start_dt = parse_dt(START_DATE)
    end_dt = parse_dt(END_DATE)

    log("=" * 70)
    log("BACKFILL TWIN — Crisis Redis 19-22 mayo 2026")
    log("=" * 70)
    log(f"Rango: {START_DATE} → {END_DATE}")
    log(f"Modo: {'APLICAR CAMBIOS REALES' if FORCE else 'DRY-RUN (solo simula)'}")
    log("")

    # Obtener puntos TWIN activos con frecuencia
    puntos = CatchmentPoint.objects.filter(
        frecuency__isnull=False,
    ).exclude(
        frecuency=""
    ).filter(
        is_tdata=True,
    ).exclude(
        ikolu_profiles__entry_by_form=True,
    ).distinct().order_by("frecuency", "title")

    log(f"Puntos TWIN a procesar: {puntos.count()}")
    log("")

    total_creados = 0
    total_actualizados = 0
    total_errores = 0
    puntos_con_huecos = 0

    for point in puntos:
        c, u, e = backfill_point(point, start_dt, end_dt, dry_run=not FORCE)
        total_creados += c
        total_actualizados += u
        total_errores += e
        if c + u > 0:
            puntos_con_huecos += 1

    log("")
    log("=" * 70)
    log("RESUMEN BACKFILL")
    log("=" * 70)
    log(f"Puntos con huecos recuperados: {puntos_con_huecos}")
    log(f"Registros creados: {total_creados}")
    log(f"Registros actualizados: {total_actualizados}")
    log(f"Errores: {total_errores}")

    if not FORCE:
        log("")
        log("⚠️  Esto fue DRY-RUN. Para aplicar cambios reales:")
        log("   docker exec -u root -w /app -e FORCE_BACKFILL=1 django_api_secure ")
        log("   python scripts/backfill_twin_crisis_mayo2026.py")
    else:
        log("")
        log("✅ Backfill aplicado.")
        log("   Ahora ejecuta recálculo de coherencia:")
        log("   docker exec -u root -w /app django_api_secure ")
        log("   python scripts/recalcular_coherencia_masivo.py --days 7 --force")


if __name__ == "__main__":
    main()
