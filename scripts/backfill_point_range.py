#!/usr/bin/env python3
"""
BACKFILL PUNTO POR RANGO — Wrapper CLI del servicio de backfill histórico
=======================================================================

Consulta datos históricos de TWIN (TDATA) o NOVUS (TagoIO) para un punto
y rango de fechas, agrupa por bucket de frecuencia, guarda en BD,
y aplica procesamiento unificado (caudal L/s, nivel con offset, totales en cascada).

Este script es un thin wrapper sobre api.core.services.telemetry_backfill.
La lógica de negocio centralizada vive en ese módulo para ser reutilizada
por el endpoint /api/telemetry-reprocessor/.

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
from datetime import datetime

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz
from api.core.models import CatchmentPoint
from api.cronjobs.telemetry.controllers.backfill_processing import detect_gaps
from api.core.services.telemetry_backfill import backfill_point_from_providers

CHILE_TZ = pytz.timezone("America/Santiago")
MAX_RANGE_DAYS = 30


def log(msg):
    print(msg, flush=True)


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

    try:
        result = backfill_point_from_providers(point, start_dt, end_dt, dry_run=not args.force)
    except ValueError as e:
        log(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        log(f"❌ Error inesperado en backfill: {e}")
        sys.exit(1)

    log(f"{'[DRY-RUN] ' if not args.force else ''}Creados: {result['records_created']} | "
        f"Actualizados: {result['records_updated']} | Errores: {result['records_failed']}")

    processing = result.get("processing") or {}
    if args.force and result["records_created"] + result["records_updated"] > 0 and not args.skip_processing:
        log("\n🔄 Procesamiento unificado en cascada...")
        log(f"   Totales recalculados: {processing.get('totals_updated', 0)}")
        log(f"   Caudales procesados: {processing.get('flow_updated', 0)}")
        log(f"   Niveles procesados: {processing.get('nivel_updated', 0)}")
        log(f"   Caudales promedio: {processing.get('avg_flow_updated', 0)}")
        log(f"   total_diff actualizados: {processing.get('diff_updated', 0)}")
        log(f"   total_today_diff actualizados: {processing.get('today_diff_updated', 0)}")
    elif args.force and result["records_created"] + result["records_updated"] > 0 and args.skip_processing:
        log("\n⚠️ Procesamiento unificado omitido (--skip-processing)")
        log("   Se guardaron valores crudos. Ejecute process_backfill_range() después si lo desea.")

    if result.get("fetch_errors"):
        log(f"\n⚠️ Errores de fetch: {len(result['fetch_errors'])}")
        for err in result["fetch_errors"][:5]:
            log(f"   - {err}")

    log("\n✅ Backfill completado")


if __name__ == "__main__":
    main()
