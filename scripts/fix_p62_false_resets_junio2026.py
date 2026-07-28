#!/usr/bin/env python3
"""
Corrección de resets falsos — Punto 62 (Planta 2 P1) PF.

Contexto:
- 2026-06-17 22:41, 2026-06-18 01:46 y 2026-06-18 03:31 UTC se detectaron
  3 resets "PARTIAL" que NO fueron reales. Eran caídas mínimas de pulsos
  (0.7% y 0.0%) que la lógica de total.py interpretó como reinicio de contador,
  sumando ~123k m³ de addition cada vez.

Efecto:
- Registros entre 2026-06-17 22:41 y 2026-06-18 14:30 quedaron con
  total = pulses + 123568 (addition erróneo).
- CounterResetLog quedó con 3 entradas PARTIAL falsas.

Acciones:
1. Backup de InteractionDetail y CounterResetLog afectados.
2. Restaurar total = pulses para el rango afectado (factor=1000, addition=0).
3. Recalcular total_diff y total_today_diff para el rango afectado.
4. Eliminar los 3 CounterResetLog PARTIAL falsos.

Uso (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/fix_p62_false_resets_junio2026.py
Aplicar:
    docker exec -u root -w /app django_api_secure python scripts/fix_p62_false_resets_junio2026.py --apply
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from decimal import Decimal

import pytz

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django

django.setup()

from django.db import transaction
from api.core.models import CatchmentPoint, CounterResetLog, InteractionDetail


POINT_ID = 62
START_DT = pytz.UTC.localize(datetime(2026, 6, 17, 22, 41, 0))
END_DT = pytz.UTC.localize(datetime(2026, 6, 18, 14, 31, 0))
FACTOR = Decimal("1000")


def log(msg):
    print(msg, flush=True)


def safe_float(s, d=0.0):
    try:
        return float(s) if s not in (None, "", "None") else d
    except (ValueError, TypeError):
        return d


def backup_records(records, filename_prefix):
    if not records:
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"/app/backups/{filename_prefix}_{ts}.csv"
    os.makedirs("/app/backups", exist_ok=True)
    with open(backup_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        w.writeheader()
        w.writerows(records)
    return backup_path


def main():
    parser = argparse.ArgumentParser(description="Corrige resets falsos punto 62 PF")
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios (sin esto es dry-run)")
    args = parser.parse_args()

    mode = "APLICAR" if args.apply else "DRY-RUN"
    log(f"{'='*60}\nCorrección resets falsos punto {POINT_ID} — {mode}\n{'='*60}")

    point = CatchmentPoint.objects.get(id=POINT_ID)

    # 1. Registros afectados en InteractionDetail
    records_qs = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=START_DT,
        date_time_medition__lt=END_DT,
    ).order_by("date_time_medition")

    records = list(records_qs.values(
        "id", "date_time_medition", "pulses", "total", "total_diff", "total_today_diff"
    ))
    log(f"Registros InteractionDetail en rango: {len(records)}")
    if not records:
        log("No hay registros para corregir.")
        return

    # Backup
    backup_id_path = backup_records(records, f"p{POINT_ID}_interactiondetail_false_resets")
    log(f"Backup InteractionDetail: {backup_id_path}")

    # 2. CounterResetLog falsos
    false_logs = list(CounterResetLog.objects.filter(
        point_catchment=point,
        reset_type="PARTIAL",
        date_time_medition__gte=START_DT,
        date_time_medition__lt=END_DT,
    ).values())
    log(f"CounterResetLog PARTIAL falsos a eliminar: {len(false_logs)}")
    if false_logs:
        backup_log_path = backup_records(false_logs, f"p{POINT_ID}_counterresetlog_false_resets")
        log(f"Backup CounterResetLog: {backup_log_path}")

    # 3. Preparar cambios de totales
    updates = []
    for r in records:
        rid = r["id"]
        pulses = r["pulses"]
        if pulses is None:
            continue
        new_total_float = (Decimal(str(pulses)) * FACTOR) / Decimal("1000")
        if new_total_float == int(new_total_float):
            new_total_str = str(int(new_total_float))
        else:
            new_total_str = f"{float(new_total_float):.2f}"

        if r["total"] != new_total_str:
            updates.append((rid, new_total_str))

    log(f"Registros cuyo total cambiará: {len(updates)}")
    if updates:
        for rid, nt in updates[:10]:
            old = next((r["total"] for r in records if r["id"] == rid), "?")
            log(f"  id={rid}: total {old} -> {nt}")
        if len(updates) > 10:
            log(f"  ... y {len(updates)-10} más")

    if not args.apply:
        log("DRY-RUN. Usar --apply para aplicar.")
        return

    # 4. Aplicar totales
    with transaction.atomic():
        for rid, new_total_str in updates:
            InteractionDetail.objects.filter(id=rid).update(total=new_total_str)
        log(f"✅ {len(updates)} totales actualizados.")

        # 5. Eliminar logs falsos
        if false_logs:
            deleted_logs, _ = CounterResetLog.objects.filter(
                point_catchment=point,
                reset_type="PARTIAL",
                date_time_medition__gte=START_DT,
                date_time_medition__lt=END_DT,
            ).delete()
            log(f"✅ {deleted_logs} CounterResetLog PARTIAL falsos eliminados.")

    # 6. Recalcular diffs (fuera de la transacción grande para no bloquear tanto)
    recalc_from = pytz.UTC.localize(datetime(2026, 6, 17, 0, 0, 0))
    diff_regs = list(
        InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=recalc_from,
            date_time_medition__lt=END_DT,
        ).order_by("date_time_medition")
    )
    log(f"Recalculando diffs para {len(diff_regs)} registros desde {recalc_from}...")

    first_total_of_day = {}
    prev_total = None
    diff_updates = 0
    today_diff_updates = 0

    for i, r in enumerate(diff_regs):
        curr_total = safe_float(r.total, 0.0)
        day = r.date_time_medition.date()

        if day not in first_total_of_day:
            first_total_of_day[day] = curr_total

        if i == 0:
            new_diff = 0
            new_today = 0
        else:
            new_diff = max(0, int(round(curr_total - prev_total)))
            new_today = max(0, int(round(curr_total - first_total_of_day[day])))

        changed = False
        if (r.total_diff or 0) != new_diff:
            r.total_diff = new_diff
            changed = True
            diff_updates += 1
        if (r.total_today_diff or 0) != new_today:
            r.total_today_diff = new_today
            changed = True
            today_diff_updates += 1

        if changed:
            r.save(update_fields=["total_diff", "total_today_diff"])

        prev_total = curr_total

    log(f"✅ Diffs actualizados: total_diff={diff_updates}, total_today_diff={today_diff_updates}")

    # 7. Verificación
    first_affected = InteractionDetail.objects.filter(id=records[0]["id"]).first()
    last_affected = InteractionDetail.objects.filter(id=records[-1]["id"]).first()
    last_overall = InteractionDetail.objects.filter(catchment_point=point).order_by(
        "-date_time_medition"
    ).first()

    log("\nVerificación:")
    log(f"  Primer afectado: {first_affected.date_time_medition} pulses={first_affected.pulses} total={first_affected.total}")
    log(f"  Último afectado: {last_affected.date_time_medition} pulses={last_affected.pulses} total={last_affected.total}")
    log(f"  Último registro: {last_overall.date_time_medition} pulses={last_overall.pulses} total={last_overall.total} diff={last_overall.total_diff} today_diff={last_overall.total_today_diff}")

    remaining_false_logs = CounterResetLog.objects.filter(
        point_catchment=point,
        reset_type="PARTIAL",
        date_time_medition__gte=START_DT,
        date_time_medition__lt=END_DT,
    ).count()
    log(f"  Logs PARTIAL remanentes en rango: {remaining_false_logs}")


if __name__ == "__main__":
    main()
