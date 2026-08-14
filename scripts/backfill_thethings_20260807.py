#!/usr/bin/env python3
"""
BACKFILL BUCKET 18:00 UTC (14:00 CLT) — 07-Ago-2026 — Puntos NETTRA thethings (24 DGA).

Hueco global del proveedor thethings (telemetry_provider_id=2, frecuency=60): la corrida
unified_nettra_60 de las 18:04 calculó los valores pero nunca persistió el bucket 18:00 UTC.
El getter thethings no tiene histórico (solo último valor), así que se replica el vecino:

  - 18 puntos con total 17:00 == total 19:00: se copian total/flow/nivel/water_table del 17:00.
  - 6 puntos con movimiento (17,18,19,20,21,65): total = round((t17+t19)/2),
    flow/nivel/water_table = promedio 17:00/19:00.
  - total_diff   = total18 - total17
  - total_today_diff = total18 - day_first, donde day_first = total del registro 04:00 UTC
    (00:00 CLT) de ese día (convención verificada: ttd se reinicia a 0 a las 04:00 UTC).
  - date_time_last_logger / pulses / variable_values / variable_details copiados del 17:00.
  - send_dga = True (para que cron_dga.py los envíe y obtenga n_voucher).
  - is_error=False, is_partial=False, days_not_conection=0, n_voucher=NULL.

date_time_medition se guarda como hora CLT naive "2026-08-07T14:00:00" (igual que el cron);
Django la convierte a UTC al persistir.

Uso:
  python backfill_thethings_20260807.py           # dry-run (solo reporte)
  python backfill_thethings_20260807.py --force   # backup + escribir
"""

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz

from api.core.models import InteractionDetail  # noqa: E402

POINT_IDS = [12, 14, 15, 17, 18, 19, 20, 21, 22, 23, 24, 25,
             58, 65, 66, 67, 68, 72, 73, 74, 125, 127, 128, 174]

# Bucket objetivo: 18:00 UTC = 14:00 CLT del 2026-08-07
BUCKET_CLT = "2026-08-07T14:00:00"
T17_CLT = "2026-08-07T13:00:00"
T19_CLT = "2026-08-07T15:00:00"
# Registro 04:00 UTC = 00:00 CLT: baseline del "total_today_diff"
DAY_FIRST_UTC = pytz.utc.localize(datetime(2026, 8, 7, 4, 0, 0))


def as_aware(clt_str):
    """'2026-08-07T13:00:00' (CLT naive) -> datetime aware en UTC (17:00 UTC)."""
    from django.utils import timezone
    naive = datetime.strptime(clt_str, "%Y-%m-%dT%H:%M:%S")
    return timezone.make_aware(naive, timezone.get_current_timezone())


def to_int_total(v):
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (ValueError, TypeError):
        return None


def dec2(v):
    try:
        return float(round(Decimal(str(v)), 2))
    except (ValueError, TypeError):
        return 0.0


def compute_point(pid):
    rows = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__gte=as_aware(T17_CLT),
        date_time_medition__lte=as_aware(T19_CLT),
    ).order_by("date_time_medition")
    reg17 = None
    reg19 = None
    for r in rows:
        if r.date_time_medition == as_aware(T17_CLT):
            reg17 = r
        elif r.date_time_medition == as_aware(T19_CLT):
            reg19 = r

    out = {"pid": pid, "reg17": reg17, "reg19": reg19, "total": None,
           "flow": None, "nivel": None, "water_table": None,
           "total_diff": None, "total_today_diff": None,
           "pulses": None, "logger": None, "vars": None, "vdetails": None,
           "days_not_conection": 0, "mode": None}

    if reg17 is None or reg19 is None:
        out["error"] = f"faltan vecinos (17:00={reg17 is not None}, 19:00={reg19 is not None})"
        return out

    t17 = to_int_total(reg17.total)
    t19 = to_int_total(reg19.total)
    if t17 is None or t19 is None:
        out["error"] = f"total no numérico (17:00={reg17.total!r}, 19:00={reg19.total!r})"
        return out

    day_first = None
    first = (InteractionDetail.objects
             .filter(catchment_point_id=pid,
                     date_time_medition=DAY_FIRST_UTC)
             .exclude(total__isnull=True).exclude(total="").exclude(total="None")
             .first())
    if first is None:
        first = (InteractionDetail.objects
                 .filter(catchment_point_id=pid,
                         date_time_medition__gte=as_aware("2026-08-07T00:00:00"),
                         date_time_medition__lt=as_aware("2026-08-07T04:00:00"))
                 .exclude(total__isnull=True).exclude(total="").exclude(total="None")
                 .first())
    day_first = to_int_total(first.total) if first else t17

    if t17 == t19:
        out["mode"] = "replicar-17"
        out["total"] = t17
        out["flow"] = dec2(reg17.flow)
        out["nivel"] = dec2(reg17.nivel)
        out["water_table"] = dec2(reg17.water_table)
        out["total_diff"] = 0
        out["total_today_diff"] = max(0, t17 - day_first)
        out["pulses"] = reg17.pulses
        out["logger"] = reg17.date_time_last_logger
        out["vars"] = deepcopy(reg17.variable_values)
        out["vdetails"] = deepcopy(reg17.variable_details)
        out["days_not_conection"] = reg17.days_not_conection or 0
    else:
        avg_total = Decimal(t17 + t19) / 2
        total = int(avg_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        out["mode"] = "promedio-17-19"
        out["total"] = total
        out["flow"] = dec2((dec2(reg17.flow) + dec2(reg19.flow)) / 2)
        out["nivel"] = dec2((dec2(reg17.nivel) + dec2(reg19.nivel)) / 2)
        out["water_table"] = dec2((dec2(reg17.water_table) + dec2(reg19.water_table)) / 2)
        out["total_diff"] = max(0, total - t17)
        out["total_today_diff"] = max(0, total - day_first)
        out["pulses"] = reg17.pulses
        out["logger"] = reg17.date_time_last_logger
        out["vars"] = deepcopy(reg17.variable_values)
        out["vdetails"] = deepcopy(reg17.variable_details)
        out["days_not_conection"] = reg17.days_not_conection or 0
    return out


def main():
    ap = argparse.ArgumentParser(description="Backfill bucket 18:00 UTC 07-ago-2026 (24 puntos DGA thethings)")
    ap.add_argument("--force", action="store_true", help="Backup + escribir (default: dry-run)")
    args = ap.parse_args()

    from django.utils import timezone as dj_tz

    backup_rows = []
    plans = []
    errors = []
    for pid in POINT_IDS:
        out = compute_point(pid)
        if out.get("error"):
            errors.append((pid, out["error"]))
            continue
        plans.append(out)

    print("=" * 110)
    print("PLAN DE INSERCIÓN — bucket 2026-08-07 18:00 UTC (14:00 CLT)")
    print("=" * 110)
    print(f"{'pt':<4}{'modo':<14}{'total17':>10}{'total19':>10}{'total18':>10}"
          f"{'tdiff':>7}{'ttdiff':>8}{'flow':>9}{'nivel':>9}{'wt':>9}")
    for p in plans:
        print(f"{p['pid']:<4}{p['mode']:<14}{p['reg17'].total or '-':>10}{p['reg19'].total or '-':>10}"
              f"{p['total']:>10}{p['total_diff']:>7}{p['total_today_diff']:>8}"
              f"{p['flow']:>9}{p['nivel']:>9}{p['water_table']:>9}")
    for pid, e in errors:
        print(f"  !!! PUNTO {pid}: {e}")

    if not args.force:
        print("\n(dry-run — no se escribe). Revisar antes de --force.")
        return

    # ---- BACKUP ----
    for pid in POINT_IDS:
        for r in InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gte=as_aware("2026-08-07T15:00:00"),
            date_time_medition__lt=as_aware("2026-08-07T23:00:00"),
        ):
            row = {}
            for f in InteractionDetail._meta.fields:
                v = getattr(r, f.name)
                if isinstance(v, datetime):
                    v = v.strftime("%Y-%m-%dT%H:%M:%S%z")
                elif hasattr(v, "pk") and not isinstance(v, (int, float, str, bool)):
                    v = v.pk
                elif isinstance(v, Decimal):
                    v = float(v)
                elif not isinstance(v, (int, float, str, bool, type(None))):
                    v = str(v)
                row[f.name] = v
            backup_rows.append(row)
    bk_file = f"/app/backups/backup_thethings_20260807_18h_{dj_tz.now():%Y%m%d_%H%M%S}.json"
    with open(bk_file, "w") as fh:
        json.dump(backup_rows, fh, indent=1)
    print(f"\nBackup ventana (15:00-23:00 UTC) escrito en {bk_file} ({len(backup_rows)} registros)")

    # ---- ESCRITURA ----
    written = 0
    for p in plans:
        defaults = {
            "total": str(p["total"]),
            "total_diff": p["total_diff"],
            "total_today_diff": p["total_today_diff"],
            "flow": p["flow"],
            "nivel": p["nivel"],
            "water_table": p["water_table"],
            "pulses": p["pulses"] or 0,
            "date_time_last_logger": p["logger"],
            "variable_values": p["vars"],
            "variable_details": p["vdetails"],
            "days_not_conection": p["days_not_conection"],
            "is_partial": False,
            "is_error": False,
            "send_dga": True,
            "return_dga": None,
            "n_voucher": None,
            "dga_retry_count": 0,
            "dga_last_retry_at": None,
        }
        InteractionDetail.objects.update_or_create(
            catchment_point_id=p["pid"],
            date_time_medition=BUCKET_CLT,
            defaults=defaults,
        )
        written += 1
    print(f">>> Escritos {written} registros (bucket 2026-08-07 18:00 UTC)")

    # ---- VERIFICACIÓN ----
    print("\nVERIFICACIÓN POST-ESCRITURA:")
    for pid in POINT_IDS:
        r = (InteractionDetail.objects
             .filter(catchment_point_id=pid, date_time_medition=as_aware(BUCKET_CLT))
             .first())
        if r:
            print(f"  pt {pid:<4} total={r.total:<10} tdiff={r.total_diff:<5} "
                  f"ttdiff={r.total_today_diff:<6} send_dga={r.send_dga} n_voucher={r.n_voucher}")
        else:
            print(f"  pt {pid:<4} NO EXISTE")


if __name__ == "__main__":
    main()
