#!/usr/bin/env python3
import os, sys
from datetime import datetime, timedelta
import pytz
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django; django.setup()
from api.core.models import InteractionDetail, CatchmentPoint

POINT_ID = 64
UTC = pytz.UTC
LAST_BACKFILL = UTC.localize(datetime(2026, 5, 22, 12, 30, 0))
FIRST_CRON = UTC.localize(datetime(2026, 5, 22, 16, 1, 0))
FORCE = os.environ.get("FORCE_FIX", "0") == "1"

def log(msg): print(msg, flush=True)

def main():
    log(f"{'='*60}\nRelleno hueco punto {POINT_ID}\n{'='*60}")
    last = InteractionDetail.objects.filter(
        catchment_point_id=POINT_ID, date_time_medition__lte=LAST_BACKFILL
    ).order_by("-date_time_medition").values("total", "date_time_medition").first()
    if not last:
        log("No se encontró último registro."); return
    last_total = last["total"]
    log(f"Último backfill: {last['date_time_medition']} total={last_total}")

    deleted, _ = InteractionDetail.objects.filter(
        catchment_point_id=POINT_ID,
        date_time_medition__gt=LAST_BACKFILL,
        date_time_medition__lt=FIRST_CRON
    ).delete()
    log(f"Residuos eliminados en hueco: {deleted}")

    expected = []
    t = LAST_BACKFILL + timedelta(minutes=5)
    while t < FIRST_CRON:
        expected.append(t)
        t += timedelta(minutes=5)
    log(f"Buckets a crear: {len(expected)} ({expected[0]} → {expected[-1]})")

    exists = set(
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__in=expected
        ).values_list("date_time_medition", flat=True)
    )
    missing = [d for d in expected if d not in exists]
    log(f"Faltantes: {len(missing)}")

    if not FORCE:
        log("DRY-RUN. Usar FORCE_FIX=1 para aplicar.")
        return

    point = CatchmentPoint.objects.get(id=POINT_ID)
    objs = []
    for dt in missing:
        objs.append(InteractionDetail(
            date_time_medition=dt,
            pulses=0,
            total=str(last_total),
            total_diff=0,
            total_today_diff=0,
            is_error=False,
            catchment_point=point,
        ))
    InteractionDetail.objects.bulk_create(objs)
    log(f"✅ {len(objs)} registros insertados.")

if __name__ == "__main__":
    main()
