#!/usr/bin/env python3
"""
BACKFILL BUCKET 19:00 UTC (15:00 CLT) — 04-Ago-2026 — Puntos TDATA (18 DGA).

Evento global del proveedor TDATA: 34/59 puntos tdata-60 perdieron el bucket
2026-08-04 19:00 UTC. De los 21 puntos DGA afectados, este script reconstruye los 18
cuyo estándar exige ese bucket horario (MAYOR x15 + SIN_ESTANDAR x3).

Estrategia por punto (verificada empíricamente contra buckets EXISTENTES 18:00/20:00 UTC):
  - 14 puntos con histórico del totalizador (149,156,157,159,160,163,167,172,175,184,
    186,203,204,210): se REPRODUCE el bucket desde get_data_tdata_history con la misma
    convención del cron:
        bucket CLT H <- última lectura TDATA con hora CLT en [H, H+1)
        total = int(round((pulses * pulses_factor)/1000 + addition))
        flow = instantaneous_flow(raw_caudal, convert_to_lt, calculate_nivel)
        nivel = nivel_mt(raw_nivel + nivel_offset, calculate_nivel, pid, d3)
        water_table = water_table(nivel, d3)
  - 4 puntos SIN histórico del totalizador en esa ventana (158,161,209,211): se replica
    el registro vecino 18:00 UTC (total idéntico en ambos vecinos, como el backfill thethings).

Diffs calculados con la convención de la BD:
    total_diff = total18h - total del registro previo (17:00 UTC)
    total_today_diff = total18h - total del registro 04:00 UTC (00:00 CLT) de ese día.

date_time_medition se guarda como CLT naive "2026-08-04T15:00:00"; Django la convierte
a UTC al persistir. send_dga=True para que cron_dga los envíe y obtenga n_voucher.

Uso:
  python backfill_tdata_20260804.py           # dry-run (reporte)
  python backfill_tdata_20260804.py --force   # backup + escribir
"""

import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz

from api.core.models import CatchmentPoint, SchemesCatchment, Variable, InteractionDetail
from api.cronjobs.telemetry.getters.tdata import get_data_tdata_history
from api.cronjobs.telemetry.controllers.flow import instantaneous_flow
from api.cronjobs.telemetry.controllers.nivel import nivel_mt, water_table

UTC = pytz.utc

# 18 puntos DGA con laguna de dato 04-ago 19:00 UTC (estándar MAYOR/SIN_ESTANDAR)
POINT_IDS = [149, 156, 157, 158, 159, 160, 161, 163, 167, 172, 175,
             184, 186, 203, 204, 209, 210, 211]

# Puntos sin histórico de totalizador en la ventana -> réplica del vecino 18:00 UTC
REPLICATE_NEIGHBOR = {158, 161, 209, 211}

BUCKET_CLT = "2026-08-04T15:00:00"      # 19:00 UTC
T18_CLT = "2026-08-04T14:00:00"         # vecino 18:00 UTC
T17_CLT = "2026-08-04T13:00:00"         # previo 17:00 UTC
DAY_FIRST_UTC = pytz.utc.localize(datetime(2026, 8, 4, 4, 0, 0))  # 00:00 CLT

TDATA_START = datetime(2026, 8, 4, 14, 30, 0)
TDATA_END = datetime(2026, 8, 4, 15, 30, 0)


def as_aware(clt_str):
    from django.utils import timezone
    return timezone.make_aware(datetime.strptime(clt_str, "%Y-%m-%dT%H:%M:%S"),
                               timezone.get_current_timezone())


def to_int_total(v):
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (ValueError, TypeError):
        return None


def bucket_value(hist, bucket_str):
    """bucket CLT H <- última lectura con hora CLT en [H, H+1)."""
    best = None
    for it in hist:
        try:
            dt = datetime.strptime(it["date_time"], "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            continue
        if dt.strftime("%Y-%m-%dT%H:00:00") == bucket_str:
            if best is None or it["ts_ms"] > best["ts_ms"]:
                best = it
    return best


def build_from_history(pid, var_map, profile):
    """Reproduce el bucket 15:00 CLT desde el histórico (convención del cron)."""
    reg = {}
    addition = float(profile.addition or 0)
    d3 = float(profile.d3 or 0)
    nivel_offset = float(profile.nivel_offset or 0)

    tot = var_map.get("TOTALIZADO")
    if tot:
        b = bucket_value(tot["hist"], BUCKET_CLT)
        if b:
            try:
                pulses = int(float(b["value"]))
            except (ValueError, TypeError):
                pulses = 0
            factor = float(tot.get("pulses_factor") or 1000) or 1000
            reg["pulses"] = pulses
            reg["total"] = int(round((pulses * factor) / 1000.0 + addition))
        else:
            return None
    else:
        return None

    cau = var_map.get("CAUDAL")
    b = bucket_value(cau["hist"], BUCKET_CLT) if cau else None
    if b:
        try:
            raw_f = float(b["value"])
        except (ValueError, TypeError):
            raw_f = 0.0
        reg["flow"] = instantaneous_flow(raw_f, bool(cau.get("convert_to_lt")), cau.get("calculate_nivel"))
    else:
        reg["flow"] = 0.0

    niv = var_map.get("NIVEL")
    b = bucket_value(niv["hist"], BUCKET_CLT) if niv else None
    if b:
        try:
            raw_n = float(b["value"])
        except (ValueError, TypeError):
            raw_n = 0.0
        try:
            nv = float(nivel_mt(raw_n + nivel_offset, niv.get("calculate_nivel"), pid, d3))
        except (TypeError, ValueError):
            nv = 0.0
        reg["nivel"] = nv
        try:
            reg["water_table"] = float(water_table(nv, d3) or 0.0)
        except (TypeError, ValueError):
            reg["water_table"] = 0.0
    else:
        reg["nivel"] = 0.0
        reg["water_table"] = 0.0
    return reg


def copy_neighbor(reg18):
    """Replica el registro 18:00 UTC (solo total idéntico confirmado en ambos vecinos)."""
    return {
        "pulses": reg18.pulses,
        "total": to_int_total(reg18.total),
        "flow": float(reg18.flow or 0.0),
        "nivel": float(reg18.nivel or 0.0),
        "water_table": float(reg18.water_table or 0.0),
    }


def main():
    ap = argparse.ArgumentParser(description="Backfill 04-ago 19:00 UTC (18 puntos DGA tdata)")
    ap.add_argument("--force", action="store_true", help="Backup + escribir (default: dry-run)")
    args = ap.parse_args()

    from django.utils import timezone as dj_tz

    plans = []
    errors = []
    for pid in POINT_IDS:
        pt = CatchmentPoint.objects.get(id=pid)
        profile = pt.data_config_profiles.filter(is_telemetry=True).first()
        if not profile:
            errors.append((pid, "sin profile"))
            continue
        ptoken = profile.token_service
        scheme = SchemesCatchment.objects.filter(points_catchment=pt).first()
        vars_db = list(Variable.objects.filter(scheme_catchment=scheme).order_by("id"))
        provider = pt.telemetry_provider

        reg18 = InteractionDetail.objects.filter(
            catchment_point_id=pid, date_time_medition=as_aware(T18_CLT)
        ).first()

        if pid in REPLICATE_NEIGHBOR:
            if not reg18:
                errors.append((pid, "sin vecino 18:00"))
                continue
            val = copy_neighbor(reg18)
            mode = "replica-vecino"
            logger = reg18.date_time_last_logger
            vars_ = reg18.variable_values
            vdetails = reg18.variable_details
            days_nc = reg18.days_not_conection or 0
        else:
            var_map = {}
            for v in vars_db:
                if (v.type_variable or "").upper() == "CAUDAL_PROMEDIO":
                    continue
                token = v.token_service or ptoken
                hist = get_data_tdata_history(provider, token, v.str_variable, TDATA_START, TDATA_END, limit=10000)
                var_map[(v.type_variable or "").upper()] = {
                    "id": v.id, "str_variable": v.str_variable, "type_variable": v.type_variable,
                    "pulses_factor": float(v.pulses_factor or 1000), "convert_to_lt": v.convert_to_lt,
                    "calculate_nivel": v.calculate_nivel, "hist": hist,
                }
            val = build_from_history(pid, var_map, profile)
            if val is None:
                if not reg18:
                    errors.append((pid, "sin histórico y sin vecino 18:00"))
                    continue
                val = copy_neighbor(reg18)
                mode = "replica-vecino(fallback)"
                logger = reg18.date_time_last_logger
                vars_ = reg18.variable_values
                vdetails = reg18.variable_details
                days_nc = reg18.days_not_conection or 0
            else:
                mode = "historico-real"
                logger = None
                vars_ = {}
                vdetails = []
                days_nc = 0

        # Diffs con convención BD: total_diff vs registro previo (17:00), ttd vs 04:00 UTC
        prev = InteractionDetail.objects.filter(
            catchment_point_id=pid, date_time_medition=as_aware(T17_CLT)
        ).first()
        prev_total = to_int_total(prev.total) if prev else None
        day_first = None
        df = InteractionDetail.objects.filter(
            catchment_point_id=pid, date_time_medition=DAY_FIRST_UTC
        ).exclude(total__isnull=True).exclude(total="").exclude(total="None").first()
        day_first = to_int_total(df.total) if df else None

        total = val["total"]
        tdiff = max(0, total - prev_total) if prev_total is not None else 0
        ttd = max(0, total - day_first) if day_first is not None else 0

        plans.append({
            "pid": pid, "mode": mode, "total": total, "tdiff": tdiff, "ttd": ttd,
            "flow": round(val["flow"], 2), "nivel": round(val["nivel"], 2),
            "water_table": round(val["water_table"], 2), "pulses": val.get("pulses", 0),
            "logger": logger, "vars": vars_, "vdetails": vdetails,
            "days_nc": days_nc, "reg18_exists": reg18 is not None,
        })

    print("=" * 104)
    print("PLAN BACKFILL — bucket 2026-08-04 19:00 UTC (15:00 CLT) — 18 puntos DGA tdata")
    print("=" * 104)
    print(f"{'pt':<5}{'modo':<20}{'total':>10}{'tdiff':>7}{'ttd':>8}{'flow':>9}{'nivel':>9}{'wt':>9}")
    for p in plans:
        print(f"{p['pid']:<5}{p['mode']:<20}{p['total']:>10}{p['tdiff']:>7}{p['ttd']:>8}"
              f"{p['flow']:>9}{p['nivel']:>9}{p['water_table']:>9}")
    for pid, e in errors:
        print(f"  !!! PUNTO {pid}: {e}")

    if not args.force:
        print("\n(dry-run — no se escribe). Revisar antes de --force.")
        return

    # ---- BACKUP ----
    backup_rows = []
    for pid in POINT_IDS:
        for r in InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gte=as_aware("2026-08-04T17:00:00"),
            date_time_medition__lt=as_aware("2026-08-04T21:00:00"),
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
    bk_file = f"/app/backups/backup_tdata_20260804_19h_{dj_tz.now():%Y%m%d_%H%M%S}.json"
    with open(bk_file, "w") as fh:
        json.dump(backup_rows, fh, indent=1)
    print(f"\nBackup ventana (17:00-21:00 UTC) escrito en {bk_file} ({len(backup_rows)} registros)")

    # ---- ESCRITURA ----
    written = 0
    for p in plans:
        defaults = {
            "total": str(p["total"]),
            "total_diff": p["tdiff"],
            "total_today_diff": p["ttd"],
            "flow": p["flow"],
            "nivel": p["nivel"],
            "water_table": p["water_table"],
            "pulses": p["pulses"] or 0,
            "date_time_last_logger": p["logger"],
            "variable_values": p["vars"],
            "variable_details": p["vdetails"],
            "days_not_conection": p["days_nc"],
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
    print(f">>> Escritos {written} registros (bucket 2026-08-04 19:00 UTC)")

    # ---- VERIFICACIÓN ----
    print("\nVERIFICACIÓN POST-ESCRITURA:")
    for pid in POINT_IDS:
        r = (InteractionDetail.objects
             .filter(catchment_point_id=pid, date_time_medition=as_aware(BUCKET_CLT))
             .first())
        if r:
            print(f"  pt {pid:<4} total={r.total:<10} tdiff={r.total_diff:<5} "
                  f"ttd={r.total_today_diff:<6} send_dga={r.send_dga} n_voucher={r.n_voucher}")
        else:
            print(f"  pt {pid:<4} NO EXISTE")


if __name__ == "__main__":
    main()
