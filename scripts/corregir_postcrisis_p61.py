#!/usr/bin/env python3
import os, sys
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from api.core.models import InteractionDetail

POINT_ID = 61
FORCE = os.environ.get("FORCE_FIX", "0") == "1"

def log(msg):
    print(msg, flush=True)

def main():
    log("=" * 60)
    log(f"Corrección post-crisis punto {POINT_ID}")
    log("=" * 60)

    # Primer registro del 22 de mayo (UTC)
    first = (
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gte="2026-05-22T00:00:00+00:00",
            date_time_medition__lt="2026-05-23T00:00:00+00:00",
        )
        .order_by("date_time_medition")
        .values("id", "total", "date_time_medition")
        .first()
    )
    if not first:
        log("⚠️ No se encontró primer registro del 22 mayo.")
        return
    first_total = float(first["total"]) if first["total"] not in (None, "", "None") else 0.0
    log(f"Primer registro 22 mayo: {first['date_time_medition'].isoformat()} total={first_total}")

    # Registro erróneo 16:01
    r_1601 = (
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition="2026-05-22T16:01:00+00:00",
        ).first()
    )
    if r_1601:
        log(f"Registro 16:01 actual: total={r_1601.total} diff={r_1601.total_diff} today={r_1601.total_today_diff}")
    else:
        log("⚠️ No se encontró registro 16:01.")
        return

    # Todos los registros del 22 mayo (UTC)
    recs = list(
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gte="2026-05-22T00:00:00+00:00",
            date_time_medition__lt="2026-05-23T00:00:00+00:00",
        ).order_by("date_time_medition")
    )

    log(f"Registros a revisar: {len(recs)}")

    updates = []
    prev_total = first_total
    for r in recs:
        rid = r.id
        dt = r.date_time_medition
        total = float(r.total) if r.total not in (None, "", "None") else 0.0

        # Corregir 16:01
        if dt.strftime("%H:%M") == "16:01":
            correct_total = 23759
            correct_diff = max(0, correct_total - int(round(prev_total)))
            correct_today = max(0, correct_total - int(round(first_total)))
            if total != correct_total or r.total_diff != correct_diff or r.total_today_diff != correct_today:
                updates.append((rid, correct_total, correct_diff, correct_today))
                log(f"   → CORREGIR {dt.isoformat()}: total {int(total)}→{correct_total} diff {r.total_diff}→{correct_diff} today {r.total_today_diff}→{correct_today}")
            total = correct_total
        else:
            # Recalcular today_diff para todos
            correct_today = max(0, int(round(total)) - int(round(first_total)))
            if r.total_today_diff != correct_today:
                updates.append((rid, int(round(total)), r.total_diff, correct_today))
                log(f"   → AJUSTAR {dt.isoformat()}: today {r.total_today_diff}→{correct_today}")

        prev_total = total

    log(f"Total ajustes: {len(updates)}")

    if not FORCE:
        log("⚠️  Simulación. Re-ejecuta con FORCE_FIX=1")
        return

    from django.db import transaction
    with transaction.atomic():
        for rid, total, diff, today in updates:
            InteractionDetail.objects.filter(id=rid).update(
                total=str(total), total_diff=diff, total_today_diff=today
            )
    log("✅ Corrección post-crisis aplicada.")

if __name__ == "__main__":
    main()
