#!/usr/bin/env python3
"""
Corrige registros con pulses=0 falsos en mayo 2026.
Regla: mantener pulses=0 (evidencia del fallo) pero poner total = último total válido anterior.
Busca total válido tanto dentro de mayo como en registros históricos previos.

Uso:
    docker exec -u root -w /app django_api_secure python scripts/fix_mayo_pulsos_cero_keep_evidence.py
    # Para aplicar:
    docker exec -u root -w /app -e FORCE_CORRECTION=1 django_api_secure python scripts/fix_mayo_pulsos_cero_keep_evidence.py
"""

import os
import sys
import csv
from datetime import datetime

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django

django.setup()

from django.db import transaction
from api.core.models import InteractionDetail, Variable


def log(msg):
    print(msg, flush=True)


def is_valid_anchor(total_str, pulses):
    """Determina si un registro puede servir como 'ancla' de total válido."""
    if total_str is None or total_str in ("", "0", "None"):
        return False
    if pulses is None or pulses <= 0:
        return False
    try:
        return float(total_str) > 0
    except (ValueError, TypeError):
        return False


def main():
    start_time = datetime.now()
    force = os.environ.get("FORCE_CORRECTION", "0") == "1"

    # 1. Identificar puntos con variable TOTALIZADO
    log("🔍 Identificando puntos con variable TOTALIZADO...")
    points_with_totalizado = set()
    for v in Variable.objects.filter(type_variable="TOTALIZADO").select_related("scheme_catchment"):
        for p in v.scheme_catchment.points_catchment.all():
            points_with_totalizado.add(p.id)
    log(f"   {len(points_with_totalizado)} puntos con TOTALIZADO")

    # 2. Obtener registros pulses=0 en mayo
    log("📊 Obteniendo registros pulses=0 en mayo 2026...")
    qs = InteractionDetail.objects.filter(
        date_time_medition__gte="2026-05-01",
        date_time_medition__lt="2026-06-01",
        pulses=0,
        catchment_point_id__in=points_with_totalizado,
    ).order_by("catchment_point_id", "date_time_medition")

    total_regs = qs.count()
    log(f"   Total registros a evaluar: {total_regs}")

    # 3. Backup CSV
    backup_path = f"/app/backups/backup_pulsos_cero_mayo_antes_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    os.makedirs("/app/backups", exist_ok=True)
    log(f"💾 Creando backup en {backup_path}...")

    fieldnames = [
        "id", "catchment_point_id", "date_time_medition",
        "pulses", "total", "total_diff", "total_today_diff",
        "days_not_conection", "is_error", "created",
        "last_valid_total", "last_valid_date", "action",
    ]

    corrections = []
    skipped_no_prior = []
    skipped_already_ok = []
    point_records = {}

    for reg in qs.iterator(chunk_size=500):
        pid = reg.catchment_point_id
        if pid not in point_records:
            point_records[pid] = []
        point_records[pid].append(reg)

    log(f"   Agrupados en {len(point_records)} puntos")

    with open(backup_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for pid, records in point_records.items():
            # Obtener TODOS los registros del punto en mayo ordenados
            all_may_records = list(
                InteractionDetail.objects.filter(
                    catchment_point_id=pid,
                    date_time_medition__gte="2026-05-01",
                    date_time_medition__lt="2026-06-01",
                ).order_by("date_time_medition").values(
                    "id", "date_time_medition", "pulses", "total",
                )
            )

            # Construir mapa de último total válido EN MAYO para cada posición
            last_valid_total = None
            last_valid_date = None
            last_valid_in_may_by_id = {}

            for rec in all_may_records:
                rid = rec["id"]
                if is_valid_anchor(rec["total"], rec["pulses"]):
                    last_valid_total = rec["total"]
                    last_valid_date = rec["date_time_medition"]
                last_valid_in_may_by_id[rid] = (last_valid_total, last_valid_date)

            # Para registros sin ancla en mayo, buscar en historial previo (una sola vez por punto)
            historical_anchor = None
            historical_date = None
            needs_historical = any(
                last_valid_in_may_by_id.get(r.id, (None, None))[0] is None
                for r in records
            )
            if needs_historical:
                prior = InteractionDetail.objects.filter(
                    catchment_point_id=pid,
                    date_time_medition__lt="2026-05-01",
                    pulses__gt=0,
                ).exclude(total__isnull=True).exclude(total="").exclude(total="0").exclude(total="None").order_by(
                    "-date_time_medition"
                ).values("total", "date_time_medition").first()
                if prior:
                    historical_anchor = prior["total"]
                    historical_date = prior["date_time_medition"]

            # Evaluar cada registro con pulses=0
            for reg in records:
                rid = reg.id
                current_total = reg.total
                may_total, may_date = last_valid_in_may_by_id.get(rid, (None, None))

                # Priorizar ancla de mayo, luego histórica
                anchor_total = may_total if may_total is not None else historical_anchor
                anchor_date = may_date if may_total is not None else historical_date

                row = {
                    "id": rid,
                    "catchment_point_id": pid,
                    "date_time_medition": reg.date_time_medition.strftime("%Y-%m-%d %H:%M:%S"),
                    "pulses": reg.pulses,
                    "total": current_total,
                    "total_diff": reg.total_diff,
                    "total_today_diff": reg.total_today_diff,
                    "days_not_conection": reg.days_not_conection,
                    "is_error": reg.is_error,
                    "created": reg.created.strftime("%Y-%m-%d %H:%M:%S") if reg.created else "",
                    "last_valid_total": anchor_total,
                    "last_valid_date": anchor_date.strftime("%Y-%m-%d %H:%M:%S") if anchor_date else "",
                }

                if anchor_total is None:
                    row["action"] = "SKIP_NO_PRIOR_VALID"
                    skipped_no_prior.append(row)
                elif current_total == anchor_total:
                    row["action"] = "SKIP_ALREADY_OK"
                    skipped_already_ok.append(row)
                else:
                    row["action"] = f"CORRECT_TO_{anchor_total}"
                    corrections.append((rid, anchor_total, row))

                writer.writerow(row)

    log(f"   Backup completado: {backup_path}")
    log(f"   Correcciones necesarias: {len(corrections)}")
    log(f"   Ya estaban OK: {len(skipped_already_ok)}")
    log(f"   Sin total anterior válido (ni en mayo ni histórico): {len(skipped_no_prior)}")

    if not corrections:
        log("✅ No hay correcciones necesarias.")
        return

    log("\n📝 Muestra de correcciones:")
    for _, _, row in corrections[:10]:
        log(f"   Punto {row['catchment_point_id']} @ {row['date_time_medition']}: "
            f"total {repr(row['total'])} → {repr(row['last_valid_total'])}")
    if len(corrections) > 10:
        log(f"   ... y {len(corrections) - 10} más")

    if not force:
        log("\n⚠️  Para aplicar correcciones, re-ejecuta con FORCE_CORRECTION=1:")
        log("   docker exec -u root -w /app -e FORCE_CORRECTION=1 django_api_secure python scripts/fix_mayo_pulsos_cero_keep_evidence.py")
        return

    # 4. Aplicar correcciones
    log(f"\n🔧 Aplicando {len(corrections)} correcciones...")
    updated = 0
    errors = 0

    with transaction.atomic():
        for rid, new_total, row in corrections:
            try:
                InteractionDetail.objects.filter(id=rid).update(total=new_total)
                updated += 1
                if updated % 500 == 0:
                    log(f"   ... {updated} actualizados")
            except Exception as e:
                log(f"   ❌ Error en id={rid}: {e}")
                errors += 1

    log(f"\n✅ Listo!")
    log(f"   Actualizados: {updated}")
    log(f"   Errores: {errors}")
    log(f"   Tiempo total: {datetime.now() - start_time}")
    log(f"   Backup: {backup_path}")


if __name__ == "__main__":
    main()
