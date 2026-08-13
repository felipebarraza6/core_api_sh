#!/usr/bin/env python3
"""
BACKFILL TELEMETRÍA IANSA — 17 buckets horarios faltantes (julio 2026).

Recupera los buckets faltantes de los 7 puntos Iansa (2, 109, 110, 111, 152, 100, 101)
desde los proveedores (TDATA / TagoIO), replicando EXACTAMENTE la convención del cron
(telemetry_unified.py), verificada empíricamente contra registros existentes:

  - date_time_medition se guarda como hora CLT naive "YYYY-MM-DDTHH:00:00";
    Django (USE_TZ=True, TIME_ZONE=America/Santiago) la convierte a UTC al persistir,
    igual que el cron.
  - Valor por bucket:
      * TDATA  (punto 2): bucket CLT H  <- última lectura TDATA con hora CLT en [H, H+1).
      * TagoIO (6 puntos): bucket CLT H <- última lectura TagoIO con hora CLT en [(H-1), H).
  - total = int(round((pulses * pulses_factor)/1000 + addition(profile))).
  - flow      = instantaneous_flow(raw_caudal, convert_to_lt, calculate_nivel).
  - nivel     = nivel_mt(raw_nivel + nivel_offset, calculate_nivel, pid, d3).
  - water_table = water_table(nivel, d3).
  - date_time_last_logger = timestamp crudo del getter (mismo quirk de zona que el cron).
  - variable_values = valor crudo por id de variable.
  - send_dga = True (para que cron_dga.py los envíe).
  - days_not_conection = 0 (los registros vecinos existentes tienen 0).

total_diff y total_today_diff se calculan en-script para LOS REGISTROS INSERTADOS con la
misma convención de la BD existente (diff = total - registro previo; today_diff = total -
primer registro del día UTC). NO se tocan los registros existentes (recalc_diffs_for_range
sobre la ventana re-baselinearía días completos y alteraría datos históricos correctos).

Uso:
  python backfill_iansa_gap.py                  # dry-run (solo reporte)
  python backfill_iansa_gap.py --points 2       # dry-run solo punto 2
  python backfill_iansa_gap.py --force          # escribir + backup
  python backfill_iansa_gap.py --force --skip-backup
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz

from api.core.models import CatchmentPoint, SchemesCatchment, Variable, InteractionDetail
from api.cronjobs.telemetry.getters.tago import get_data_tago_history
from api.cronjobs.telemetry.getters.tdata import get_data_tdata_history
from api.cronjobs.telemetry.controllers.flow import instantaneous_flow
from api.cronjobs.telemetry.controllers.nivel import nivel_mt, water_table

CHILE = pytz.timezone("America/Santiago")
UTC = pytz.utc

POINT_IDS = [2, 109, 110, 111, 152, 100, 101]

BUCKETS_CLT = (
    ["2026-07-04T21:00:00", "2026-07-04T22:00:00"]
    + ["2026-07-05T23:00:00"]
    + [f"2026-07-06T{h:02d}:00:00" for h in range(0, 14)]
)
BUCKET_DTS = [datetime.strptime(b, "%Y-%m-%dT%H:00:00") for b in BUCKETS_CLT]

WINDOW_START_UTC = datetime(2026, 7, 4, 18, 0, 0, tzinfo=UTC)
WINDOW_END_UTC = datetime(2026, 7, 7, 0, 0, 0, tzinfo=UTC)

# TDATA: getter interpreta date_time como hora CLT del sensor; el filtro del API
# usa el epoch del "wall-clock", así que se pasan datetimes CLT naive (como el probe).
TDATA_START = datetime(2026, 7, 4, 19, 0, 0)
TDATA_END = datetime(2026, 7, 6, 15, 0, 0)
# TagoIO: date_time es UTC real.
TAGO_START = datetime(2026, 7, 4, 15, 0, 0)
TAGO_END = datetime(2026, 7, 7, 0, 0, 0)


def fetch_history(var, token, provider, handler):
    if handler == "tdata":
        return get_data_tdata_history(provider, token, var.str_variable, TDATA_START, TDATA_END, limit=30000)
    return get_data_tago_history(provider, token, var.str_variable, TAGO_START, TAGO_END)


def bucket_value_tdata(hist, bucket_str):
    """Bucket CLT H <- última lectura TDATA con hora CLT en [H, H+1)."""
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


def bucket_value_tago(hist, bucket_dt):
    """Bucket CLT H <- última lectura TagoIO con hora CLT en [(H-1):00, H:00)."""
    lo = bucket_dt - timedelta(hours=1)
    best = None
    for it in hist:
        try:
            dt = datetime.strptime(it["date_time"], "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            continue
        clt = UTC.localize(dt).astimezone(CHILE).replace(tzinfo=None)
        if lo <= clt < bucket_dt:
            if best is None or it["ts_ms"] > best["raw"]["ts_ms"]:
                best = {"raw": it, "clt": clt}
    return best


def compute_register(pid, profile, var_map, bucket_dt, totals):
    """Construye el dict de campos para un bucket. totals: dict previo."""
    d3 = float(profile.d3 or 0)
    nivel_offset = float(profile.nivel_offset or 0)
    addition = float(profile.addition or 0)

    reg = {"date_time_medition": bucket_dt.strftime("%Y-%m-%dT%H:00:00"),
           "is_error": False, "is_partial": False, "send_dga": True,
           "days_not_conection": 0, "variable_values": {}, "variable_details": []}

    tot = var_map.get("TOTALIZADO")
    if tot and tot.get("bucket"):
        raw = tot["bucket"]["raw"]["value"]
        try:
            pulses = int(float(raw))
        except (ValueError, TypeError):
            pulses = 0
        factor = float(tot.get("pulses_factor") or 1000) or 1000
        total = int(round((pulses * factor) / 1000.0 + addition))
        reg["pulses"] = pulses
        reg["total"] = str(total)
        reg["total_diff"] = max(0, total - totals.get("total", total))
        reg["total_today_diff"] = max(0, total - totals.get("day_first", total))
        reg["variable_values"][str(tot["id"])] = raw
    else:
        reg["pulses"] = 0
        reg["total"] = str(totals.get("total", 0))
        reg["total_diff"] = 0
        reg["total_today_diff"] = max(0, totals.get("total", 0) - totals.get("day_first", totals.get("total", 0)))

    cau = var_map.get("CAUDAL")
    if cau and cau.get("bucket"):
        raw = cau["bucket"]["raw"]["value"]
        try:
            raw_f = float(raw)
        except (ValueError, TypeError):
            raw_f = 0.0
        reg["flow"] = instantaneous_flow(raw_f, bool(cau.get("convert_to_lt")), cau.get("calculate_nivel"))
        reg["variable_values"][str(cau["id"])] = raw
    else:
        reg["flow"] = 0.0

    niv = var_map.get("NIVEL")
    if niv and niv.get("bucket"):
        raw = niv["bucket"]["raw"]["value"]
        try:
            raw_f = float(raw)
        except (ValueError, TypeError):
            raw_f = 0.0
        nivel = nivel_mt(raw_f + nivel_offset, niv.get("calculate_nivel"), pid, d3)
        try:
            nivel_f = float(nivel)
        except (ValueError, TypeError):
            nivel_f = 0.0
        reg["nivel"] = nivel_f
        try:
            reg["water_table"] = float(water_table(nivel_f, d3) or 0.0)
        except (ValueError, TypeError):
            reg["water_table"] = 0.0
        reg["variable_values"][str(niv["id"])] = raw
    else:
        reg["nivel"] = 0.0
        reg["water_table"] = 0.0

    # date_time_last_logger: mayor timestamp crudo entre las variables con dato
    # (misma semántica que best_date_time_last_logger del cron)
    max_lg = None
    for t, m in var_map.items():
        b = m.get("bucket")
        if b:
            raw_dt = b["raw"]["date_time"]
            if max_lg is None or raw_dt > max_lg:
                max_lg = raw_dt
    reg["date_time_last_logger"] = max_lg

    # variable_details (compatibilidad legacy): solo variables con lectura
    reg["variable_details"] = [
        {
            "str_variable": m["str_variable"],
            "type_variable": m["type_variable"],
            "value": m["bucket"]["raw"]["value"],
            "success": True,
        }
        for t, m in sorted(var_map.items()) if m.get("bucket")
    ]

    reg["_src"] = {}
    for t in ("TOTALIZADO", "CAUDAL", "NIVEL"):
        b = var_map.get(t, {}).get("bucket")
        if b:
            reg["_src"][t] = {"time_raw": b["raw"]["date_time"], "clt": b.get("clt") and b["clt"].strftime("%Y-%m-%d %H:%M")}
    return reg


def process_point(pid, force, skip_backup, changed):
    point = CatchmentPoint.objects.get(id=pid)
    profile = point.data_config_profiles.filter(is_telemetry=True).first()
    if not profile:
        print(f"PUNTO {pid}: sin profile is_telemetry. SKIP")
        return
    ptoken = profile.token_service
    scheme = SchemesCatchment.objects.filter(points_catchment=point).first()
    vars_db = list(Variable.objects.filter(scheme_catchment=scheme).order_by("id"))

    default_handler = point.telemetry_provider.handler_name if point.telemetry_provider else "tdata"

    var_map = {}
    for v in vars_db:
        if (v.type_variable or "").upper() == "CAUDAL_PROMEDIO":
            continue
        token = v.token_service or ptoken
        provider = v.provider if v.provider_id else point.telemetry_provider
        handler = provider.handler_name if provider else default_handler
        hist = fetch_history(v, token, provider, handler)
        var_map[(v.type_variable or "").upper()] = {
            "id": v.id, "str_variable": v.str_variable, "type_variable": v.type_variable,
            "pulses_factor": float(v.pulses_factor or 1000),
            "convert_to_lt": v.convert_to_lt, "calculate_nivel": v.calculate_nivel,
            "handler": handler, "hist": hist,
        }

    # Bucketizar por variable
    for t, m in var_map.items():
        m["buckets"] = {}
        for bd in BUCKET_DTS:
            bs = bd.strftime("%Y-%m-%dT%H:00:00")
            if m["handler"] == "tdata":
                item = bucket_value_tdata(m["hist"], bs)
                if item:
                    m["buckets"][bs] = {"raw": item, "clt": None}
            else:
                item = bucket_value_tago(m["hist"], bd)
                if item:
                    m["buckets"][bs] = item

    print("=" * 100)
    print(f"PUNTO {pid} | {point.title} | provider={default_handler} | "
          f"d3={profile.d3} addition={profile.addition} nivel_offset={profile.nivel_offset}")
    for t, m in sorted(var_map.items()):
        cov = sum(1 for b in BUCKETS_CLT if m["buckets"].get(b))
        print(f"  var {m['type_variable']:<8} id={m['id']} str={m['str_variable']:<12} "
              f"handler={m['handler']:<5} factor={m['pulses_factor']:g} "
              f"convert_lt={m['convert_to_lt']} calc_nivel={m['calculate_nivel']} "
              f"buckets_con_dato={cov}/{len(BUCKETS_CLT)}")

    # Construir registros en orden cronológico
    inserts = []
    totals = {"total": None, "day": None, "day_first": None}

    base = (
        InteractionDetail.objects.filter(
            catchment_point_id=pid, date_time_medition__lt=WINDOW_START_UTC
        )
        .exclude(total__isnull=True).exclude(total="").exclude(total="None").exclude(total="0")
        .order_by("-date_time_medition").first()
    )
    if base:
        totals["total"] = int(round(float(base.total)))
        totals["day"] = base.date_time_medition.date()
        totals["day_first"] = totals["total"]

    for bd in BUCKET_DTS:
        bs = bd.strftime("%Y-%m-%dT%H:00:00")
        # UTC date del bucket (agrupación de día igual que recalc_diffs_for_range)
        utc_dt = CHILE.localize(bd).astimezone(UTC)
        day = utc_dt.date()

        for t, m in var_map.items():
            m["bucket"] = m["buckets"].get(bs)

        # Baseline del día UTC: primer registro de ese día (existente o insertado)
        if totals["day"] != day:
            totals["day"] = day
            totals["day_first"] = None
        if totals["day_first"] is None:
            # buscar primer registro existente del día (puede estar en BD antes del bucket)
            first_day = (
                InteractionDetail.objects.filter(
                    catchment_point_id=pid, date_time_medition__date=day
                )
                .exclude(total__isnull=True).exclude(total="").exclude(total="None")
                .order_by("date_time_medition").first()
            )
            if first_day:
                totals["day_first"] = int(round(float(first_day.total)))

        has_tot = bool(var_map.get("TOTALIZADO", {}).get("bucket"))
        missing = [t for t in ("TOTALIZADO", "CAUDAL", "NIVEL")
                   if t in var_map and not var_map[t].get("bucket")]
        if not has_tot:
            # Sin lectura de totalizador: no insertar (evita totales falsos)
            print(f"  !!! {bs}: SIN lectura TOTALIZADO {('(falta: '+','.join(missing)+')') if missing else ''}. NO INSERTADO.")
            continue

        reg = compute_register(pid, profile, var_map, bd, totals)
        totals["total"] = int(round(float(reg["total"])))
        if totals["day_first"] is None:
            totals["day_first"] = totals["total"]
        inserts.append((bs, reg, missing))

    # ---- Reporte de coherencia (window completa existente + insertado) ----
    existing = list(
        InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gte=WINDOW_START_UTC,
            date_time_medition__lt=WINDOW_END_UTC,
        ).order_by("date_time_medition").values("date_time_medition", "total", "total_diff", "total_today_diff")
    )
    merged = []
    for e in existing:
        if e["total"] not in (None, "", "None"):
            try:
                merged.append((e["date_time_medition"], int(round(float(e["total"])))))
            except (ValueError, TypeError):
                pass
    for bs, reg, _ in inserts:
        utc_dt = CHILE.localize(datetime.strptime(bs, "%Y-%m-%dT%H:00:00")).astimezone(UTC)
        merged.append((utc_dt, int(round(float(reg["total"])))))
    merged.sort(key=lambda x: x[0])

    # Aplicar a los registros a insertar los diffs calculados sobre la línea de tiempo
    # mergeada (convención idéntica a recalc_diffs_for_range: diff vs previo, today_diff
    # vs primer total del día UTC), que sí contempla los registros existentes intercalados.
    print(f"  Registros a insertar: {len(inserts)}/{len(BUCKETS_CLT)}")

    prev_total = None
    day = None
    day_first = None
    sim = {}
    for utc_dt, t in merged:
        d = utc_dt.date()
        if d != day:
            day = d
            day_first = t
        td = max(0, t - prev_total) if prev_total is not None else 0
        ttd = max(0, t - day_first)
        sim[utc_dt] = (t, td, ttd)
        prev_total = t

    for bs, reg, _ in inserts:
        utc_dt = CHILE.localize(datetime.strptime(bs, "%Y-%m-%dT%H:00:00")).astimezone(UTC)
        _, td, ttd = sim[utc_dt]
        reg["total_diff"] = td
        reg["total_today_diff"] = ttd

    for bs, reg, missing in inserts:
        src = reg["_src"]
        src_line = " | ".join(f"{k}:{v['time_raw']}" + (f" CLT({v['clt']})" if v.get('clt') else "") for k, v in src.items())
        flags = f" [SIN: {','.join(missing)}]" if missing else ""
        print(f"    {bs} -> pul={reg['pulses']} total={reg['total']} tdiff={reg['total_diff']} "
              f"ttdiff={reg['total_today_diff']} flow={reg['flow']} nivel={reg['nivel']} "
              f"wt={reg['water_table']} logger={reg.get('date_time_last_logger')}{flags}\n        src: {src_line}")

    # Monotonicidad en la ventana
    bad = []
    prev_t = None
    for utc_dt, t in merged:
        if prev_t is not None and t < prev_t:
            bad.append((utc_dt, t, prev_t))
        prev_t = t
    if bad:
        print(f"  !!! NO MONOTÓNICO ({len(bad)}): {bad[:5]}")
    else:
        print("  Monotonicidad de totales en ventana: OK")

    if not force:
        print("  (dry-run — no se escribe)")
        return

    # ---- ESCRITURA ----
    if not skip_backup:
        from django.utils import timezone as dj_tz
        backup_rows = []
        for r in InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gte=WINDOW_START_UTC,
            date_time_medition__lt=WINDOW_END_UTC,
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
        bk_file = f"/tmp/backfill_iansa_backup_p{pid}_{dj_tz.now():%Y%m%d_%H%M%S}.json"
        with open(bk_file, "w") as fh:
            json.dump(backup_rows, fh, indent=1)
        print(f"  Backup ventana escrito en {bk_file} ({len(backup_rows)} registros)")
        changed["backups"].append(bk_file)

    written = 0
    for bs, reg, missing in inserts:
        defaults = {k: v for k, v in reg.items() if not k.startswith("_") and k != "date_time_medition"}
        InteractionDetail.objects.update_or_create(
            catchment_point_id=pid,
            date_time_medition=bs,
            defaults=defaults,
        )
        written += 1
    print(f"  >>> Escritos {written} registros (punto {pid})")

    changed["inserted"][pid] = written


def main():
    ap = argparse.ArgumentParser(description="Backfill 17 buckets Iansa jul-2026")
    ap.add_argument("--points", default=",".join(str(p) for p in POINT_IDS))
    ap.add_argument("--force", action="store_true", help="Escribir en BD (default: dry-run)")
    ap.add_argument("--skip-backup", action="store_true", help="No escribir backup JSON")
    args = ap.parse_args()

    pids = [int(x) for x in args.points.split(",") if x.strip()]
    changed = {"inserted": {}, "backups": []}
    for pid in pids:
        process_point(pid, args.force, args.skip_backup, changed)
    print("\n" + "=" * 100)
    if args.force:
        print(f"RESULTADO: {sum(changed['inserted'].values())} registros escritos")
        print(f"Backups: {changed['backups']}")
    else:
        print("DRY-RUN completado (nada escrito). Revisar reporte antes de --force.")


if __name__ == "__main__":
    main()
