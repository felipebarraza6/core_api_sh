#!/usr/bin/env python3
"""
BACKFILL PUNTO POR RANGO — Recuperación histórica on-demand con procesamiento completo
======================================================================================

Consulta datos históricos de TWIN (TDATA) o NOVUS (TagoIO) para un punto
y rango de fechas, agrupa por bucket de frecuencia, guarda en BD,
y aplica procesamiento unificado (caudal L/s, nivel con offset, totales en cascada).

MODOS:
  backfill   — Ingesta + procesamiento completo (default)
  gap_detect — Solo detecta y muestra huecos sin modificar BD

USO (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/backfill_point_range.py --point-id 1 --start "2026-05-19T20:00:00" --end "2026-05-22T12:00:00"

USO (aplicar):
    docker exec -u root -w /app django_api_secure python scripts/backfill_point_range.py --point-id 1 --start "2026-05-19T20:00:00" --end "2026-05-22T12:00:00" --force

USO (detectar gaps):
    docker exec -u root -w /app django_api_secure python scripts/backfill_point_range.py --point-id 1 --mode gap_detect
"""

import os
import sys
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz
from django.db import transaction
from api.core.models import (
    CatchmentPoint, InteractionDetail, Variable,
    SchemesCatchment, ProfileDataConfigCatchment
)
from api.cronjobs.telemetry.getters.tdata import get_data_tdata_history
from api.cronjobs.telemetry.getters.tago import get_data_tago_history
from api.cronjobs.telemetry.controllers.backfill_processing import (
    process_backfill_range,
    detect_gaps,
)

CHILE_TZ = pytz.timezone("America/Santiago")
MAX_RANGE_DAYS = 30


def log(msg):
    print(msg, flush=True)


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


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
        return dt.replace(second=0, microsecond=0)


def get_provider_history_func(point):
    """Devuelve la función de histórico según el tipo de punto."""
    if point.is_tdata:
        return get_data_tdata_history
    elif point.is_novus:
        return get_data_tago_history
    return None


def backfill_point(point, start_dt, end_dt, dry_run=True):
    """
    Backfill de un punto. Retorna (creados, actualizados, errores, skipped).
    """
    point_id = point.id
    freq_str = point.frecuency or "60"
    try:
        freq_min = int(freq_str)
    except ValueError:
        freq_min = 60

    history_func = get_provider_history_func(point)
    if not history_func:
        log(f"  ⚠️ Punto {point_id} ({point.title}): provider no soportado para histórico")
        return 0, 0, 0, 0

    scheme = SchemesCatchment.objects.filter(points_catchment=point).first()
    if not scheme:
        log(f"  ⚠️ Punto {point_id} ({point.title}): sin esquema")
        return 0, 0, 0, 0

    profile = point.data_config_profiles.filter(is_telemetry=True).first()
    if not profile:
        log(f"  ⚠️ Punto {point_id} ({point.title}): sin perfil de telemetría")
        return 0, 0, 0, 0

    variables = list(Variable.objects.filter(scheme_catchment=scheme).select_related('provider'))
    if not variables:
        log(f"  ⚠️ Punto {point_id} ({point.title}): sin variables")
        return 0, 0, 0, 0

    point_token = profile.token_service or ""
    if not point_token:
        log(f"  ⚠️ Punto {point_id} ({point.title}): sin token")
        return 0, 0, 0, 0

    # Buckets existentes en el rango
    existing = set(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=start_dt,
            date_time_medition__lt=end_dt,
        ).values_list("date_time_medition", flat=True)
    )
    existing_strs = {dt.strftime("%Y-%m-%dT%H:%M:%S") for dt in existing}

    log(f"  📍 Punto {point_id} ({point.title}) frec={freq_min}min | Provider={'TWIN' if point.is_tdata else 'NOVUS'}")

    # Consultar histórico por variable y agrupar
    bucket_data = {}  # bucket_str -> {var_type: {"value": X, "ts_str": Y}}

    for var in variables:
        str_variable = var.str_variable
        provider = var.provider
        var_type = var.type_variable

        try:
            history = history_func(
                provider=provider,
                token_service=point_token,
                str_variable=str_variable,
                start_dt=start_dt.astimezone(timezone.utc).replace(tzinfo=None),
                end_dt=end_dt.astimezone(timezone.utc).replace(tzinfo=None),
                limit=10000,
            )
        except Exception as e:
            log(f"    ❌ Error consultando {str_variable}: {e}")
            continue

        log(f"    Variable {str_variable} ({var_type}): {len(history)} registros crudos")

        for item in history:
            item_dt = datetime.strptime(item["date_time"], "%Y-%m-%dT%H:%M:%S")
            item_dt = pytz.utc.localize(item_dt).astimezone(CHILE_TZ)
            bucket = truncate_to_freq(item_dt, freq_min)
            bucket_str = bucket.strftime("%Y-%m-%dT%H:%M:%S")

            if bucket_str not in bucket_data:
                bucket_data[bucket_str] = {}

            # Para cada bucket, tomar el valor del timestamp más reciente
            if var_type not in bucket_data[bucket_str] or item["ts_ms"] > bucket_data[bucket_str][var_type]["ts_ms"]:
                bucket_data[bucket_str][var_type] = {
                    "value": item["value"],
                    "ts_ms": item["ts_ms"],
                    "ts_str": item["date_time"],
                }

    if not bucket_data:
        log(f"    ⚠️ Sin datos históricos")
        return 0, 0, 0, 0

    creados = 0
    actualizados = 0
    errores = 0
    skipped = 0

    for bucket_str in sorted(bucket_data.keys()):
        vars_in_bucket = bucket_data[bucket_str]

        # Construir registro
        created_register = {
            "date_time_medition": bucket_str,
            "is_error": False,
            "is_partial": False,
            "variable_details": [],
            "variable_values": {},
        }

        # Determinar timestamp del logger (el más reciente entre variables)
        best_ts = None
        for vt, info in vars_in_bucket.items():
            if best_ts is None or info["ts_str"] > best_ts:
                best_ts = info["ts_str"]
        created_register["date_time_last_logger"] = best_ts

        # Asignar valores según tipo de variable
        has_totalizador = False
        for var in variables:
            var_type = var.type_variable
            if var_type not in vars_in_bucket:
                continue
            info = vars_in_bucket[var_type]
            value = info["value"]

            if var_type == "TOTALIZADO":
                try:
                    created_register["pulses"] = int(float(value))
                    has_totalizador = True
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

    log(f"    {'[DRY-RUN] ' if dry_run else ''}Creados: {creados} | Actualizados: {actualizados} | Errores: {errores}")
    return creados, actualizados, errores, skipped


def recalc_totals_for_range(point, start_dt, end_dt):
    """
    Recalcula totales en cascada SOLO para registros del rango que tienen total vacío.
    Retorna número de registros actualizados.
    """
    from api.core.models import ProfileDataConfigCatchment

    point_id = point.id
    factor = 1000
    v = Variable.objects.filter(type_variable="TOTALIZADO", scheme_catchment__points_catchment=point).first()
    if v and v.pulses_factor:
        factor = v.pulses_factor

    # Obtener TODOS los registros del punto ordenados
    all_records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "pulses", "total"
        )
    )
    if not all_records:
        return 0

    # Encontrar base pre-rango
    last_real_pulses = None
    last_total = None
    updated = 0

    for r in all_records:
        rid = r["id"]
        dt = r["date_time_medition"]
        in_range = start_dt <= dt < end_dt
        current_pulses = r["pulses"]
        old_total_str = r["total"]

        # Si es válido pre-rango, usarlo como base
        if not in_range:
            if current_pulses is not None and current_pulses > 0 and old_total_str not in (None, "", "0", "None"):
                try:
                    last_total = float(old_total_str)
                    last_real_pulses = float(current_pulses)
                except (ValueError, TypeError):
                    pass
            continue

        # Si no tiene pulses, no recalcular
        if current_pulses is None:
            continue

        # Si pulses=0 pero tenemos last_total válido, propagar el último total
        # para mantener monotonicidad (sensor desconectado / sin consumo)
        if current_pulses == 0 and last_total is not None:
            new_total_rounded = round_total(last_total)
            if old_total_str in (None, "", "0", "None"):
                InteractionDetail.objects.filter(id=rid).update(
                    total=str(new_total_rounded),
                    total_diff=0,
                )
                updated += 1
            continue

        if last_real_pulses is None or last_total is None:
            # Sin base, usar addition del perfil
            profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_id).first()
            addition = float(profile.addition) if profile and profile.addition else 0.0
            cp = float(current_pulses)
            new_total = (cp * factor) / 1000.0 + addition
            last_real_pulses = cp
        else:
            cp = float(current_pulses)
            if cp >= last_real_pulses:
                diff = cp - last_real_pulses
            else:
                diff = cp  # Reset
            new_total = last_total + (diff * factor) / 1000.0
            last_real_pulses = cp

        last_total = new_total
        new_total_rounded = round_total(new_total)

        # Solo actualizar si el total cambió significativamente o estaba vacío
        try:
            old_total = float(old_total_str) if old_total_str not in (None, "", "None") else 0.0
        except (ValueError, TypeError):
            old_total = 0.0

        if old_total_str in (None, "", "0", "None") or abs(round_total(old_total) - new_total_rounded) > 0:
            InteractionDetail.objects.filter(id=rid).update(total=str(new_total_rounded))
            updated += 1

    return updated


def recalc_diffs_for_range(point, start_dt, end_dt):
    """Recalcula total_diff y total_today_diff para registros del rango."""
    point_id = point.id
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=start_dt,
            date_time_medition__lt=end_dt,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "total", "total_diff", "total_today_diff"
        )
    )
    if not records:
        return 0, 0

    # Base pre-rango
    prior = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__lt=start_dt,
    ).exclude(total__isnull=True).exclude(total="").exclude(total="0").exclude(total="None").order_by(
        "-date_time_medition"
    ).values("total").first()

    prev_total = float(prior["total"]) if prior else 0.0
    diff_updates = 0
    today_diff_updates = 0
    first_total_of_day = {}
    current_day = None

    for r in records:
        rid = r["id"]
        try:
            curr_total = float(r["total"]) if r["total"] not in (None, "", "None") else 0.0
        except (ValueError, TypeError):
            curr_total = 0.0

        day = r["date_time_medition"].date()
        if current_day != day:
            current_day = day
            first_total_of_day[day] = curr_total

        # total_diff
        new_diff = max(0, round_total(curr_total) - round_total(prev_total))
        old_diff = r["total_diff"] or 0
        if new_diff != old_diff:
            InteractionDetail.objects.filter(id=rid).update(total_diff=new_diff)
            diff_updates += 1

        # total_today_diff
        first_total = first_total_of_day.get(day, 0.0)
        new_today_diff = max(0, round_total(curr_total) - round_total(first_total))
        old_today_diff = r["total_today_diff"] or 0
        if new_today_diff != old_today_diff:
            InteractionDetail.objects.filter(id=rid).update(total_today_diff=new_today_diff)
            today_diff_updates += 1

        prev_total = curr_total

    return diff_updates, today_diff_updates


def main():
    parser = argparse.ArgumentParser(description="Backfill histórico por punto y rango")
    parser.add_argument("--point-id", type=int, required=True)
    parser.add_argument("--start", help="YYYY-MM-DDTHH:MM:SS (requerido para backfill)")
    parser.add_argument("--end", help="YYYY-MM-DDTHH:MM:SS (requerido para backfill)")
    parser.add_argument("--mode", choices=["backfill", "gap_detect"], default="backfill",
                        help="backfill: ingesta+procesa | gap_detect: solo muestra huecos")
    parser.add_argument("--force", action="store_true", help="Aplicar cambios reales (solo backfill)")
    parser.add_argument("--skip-processing", action="store_true",
                        help="Saltar procesamiento unificado: solo ingesta cruda (solo backfill)")
    args = parser.parse_args()

    try:
        point = CatchmentPoint.objects.get(id=args.point_id)
    except CatchmentPoint.DoesNotExist:
        log(f"❌ Punto {args.point_id} no existe")
        sys.exit(1)

    # ==================== MODO GAP DETECT ====================
    if args.mode == "gap_detect":
        log("=" * 70)
        log(f"GAP DETECT — Punto {point.id} ({point.title})")
        log("=" * 70)

        start_dt = None
        end_dt = None
        if args.start and args.end:
            start_dt = CHILE_TZ.localize(datetime.strptime(args.start, "%Y-%m-%dT%H:%M:%S"))
            end_dt = CHILE_TZ.localize(datetime.strptime(args.end, "%Y-%m-%dT%H:%M:%S"))

        gaps = detect_gaps(point, start_dt, end_dt)
        if not gaps:
            log("✅ No se detectaron gaps")
        else:
            log(f"🔍 Gaps detectados: {len(gaps)}")
            for g in gaps:
                log(f"   {g['start_gap']} → {g['end_gap']} ({g['missing_count']} registros faltantes)")
        sys.exit(0)

    # ==================== MODO BACKFILL ====================
    if not args.start or not args.end:
        log("❌ --start y --end son requeridos para modo backfill")
        sys.exit(1)

    start_dt = CHILE_TZ.localize(datetime.strptime(args.start, "%Y-%m-%dT%H:%M:%S"))
    end_dt = CHILE_TZ.localize(datetime.strptime(args.end, "%Y-%m-%dT%H:%M:%S"))

    if end_dt <= start_dt:
        log("❌ end debe ser mayor que start")
        sys.exit(1)

    if (end_dt - start_dt).days > MAX_RANGE_DAYS:
        log(f"❌ Rango máximo permitido: {MAX_RANGE_DAYS} días")
        sys.exit(1)

    log("=" * 70)
    log(f"BACKFILL Punto {point.id} ({point.title})")
    log(f"Rango: {args.start} → {args.end}")
    log(f"Modo: {'APLICAR' if args.force else 'DRY-RUN'}")
    log("=" * 70)

    c, u, e, s = backfill_point(point, start_dt, end_dt, dry_run=not args.force)

    if args.force and c + u > 0 and not args.skip_processing:
        log("\n🔄 Procesamiento unificado en cascada...")
        results = process_backfill_range(point, start_dt, end_dt)
        log(f"   Totales recalculados: {results['totals_updated']}")
        log(f"   Caudales procesados: {results['flow_updated']}")
        log(f"   Niveles procesados: {results['nivel_updated']}")
        log(f"   Caudales promedio: {results['avg_flow_updated']}")
        log(f"   total_diff actualizados: {results['diff_updated']}")
        log(f"   total_today_diff actualizados: {results['today_diff_updated']}")
    elif args.force and c + u > 0 and args.skip_processing:
        log("\n⚠️ Procesamiento unificado omitido (--skip-processing)")
        log("   Se guardaron valores crudos. Ejecute process_backfill_range() después si lo desea.")

    log("\n✅ Backfill completado")


if __name__ == "__main__":
    main()
