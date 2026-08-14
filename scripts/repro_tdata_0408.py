#!/usr/bin/env python3
"""
VERIFICACIÓN DE REPRODUCCIÓN — TDATA bucket existentes vs histórico.

Para puntos tdata afectados el 04-ago, reproduce el bucket 20:00 UTC (16:00 CLT)
y 18:00 UTC (14:00 CLT) EXISTENTES usando la misma convención del cron/backfill_iansa:
  - bucket CLT H <- última lectura TDATA con hora CLT en [H, H+1)
  - total = int(round((pulses * pulses_factor)/1000 + addition))
y compara contra lo almacenado en core_interactiondetail.

Si la reproducción coincide -> la reconstrucción del bucket 19:00 UTC será coherente.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from api.core.models import CatchmentPoint, SchemesCatchment, Variable, InteractionDetail
from api.cronjobs.telemetry.getters.tdata import get_data_tdata_history
from api.cronjobs.telemetry.controllers.flow import instantaneous_flow
from api.cronjobs.telemetry.controllers.nivel import nivel_mt, water_table

POINTS = [149, 156, 157, 159, 160, 163, 167, 172, 175, 184, 186, 203, 204, 210]

# Ventana amplia: cubre buckets CLT 13:00..17:00
TDATA_START = datetime(2026, 8, 4, 13, 0, 0)
TDATA_END = datetime(2026, 8, 4, 17, 30, 0)

TARGETS = {"2026-08-04T14:00:00": "18:00 UTC", "2026-08-04T16:00:00": "20:00 UTC"}


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


for pid in POINTS:
    pt = CatchmentPoint.objects.get(id=pid)
    profile = pt.data_config_profiles.filter(is_telemetry=True).first()
    if not profile:
        print(f"{pid}: sin profile"); continue
    ptoken = profile.token_service
    scheme = SchemesCatchment.objects.filter(points_catchment=pt).first()
    vars_db = list(Variable.objects.filter(scheme_catchment=scheme).order_by("id"))
    provider = pt.telemetry_provider
    if not provider:
        print(f"{pid}: sin provider"); continue

    addition = float(profile.addition or 0)
    d3 = float(profile.d3 or 0)
    nivel_offset = float(profile.nivel_offset or 0)

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

    print(f"=== PUNTO {pid} ({pt.title}) addition={addition} d3={d3}")
    for bstr, label in TARGETS.items():
        tot = var_map.get("TOTALIZADO")
        cau = var_map.get("CAUDAL")
        niv = var_map.get("NIVEL")
        if tot and bucket_value(tot["hist"], bstr):
            raw = bucket_value(tot["hist"], bstr)["value"]
            pulses = int(float(raw))
            total = int(round((pulses * tot["pulses_factor"]) / 1000.0 + addition))
        else:
            total = None
        flow = 0.0
        if cau and bucket_value(cau["hist"], bstr):
            flow = instantaneous_flow(float(bucket_value(cau["hist"], bstr)["value"]),
                                      bool(cau.get("convert_to_lt")), cau.get("calculate_nivel"))
        nivel = 0.0
        wt = 0.0
        if niv and bucket_value(niv["hist"], bstr):
            raw_n = float(bucket_value(niv["hist"], bstr)["value"])
            nivel = nivel_mt(raw_n + nivel_offset, niv.get("calculate_nivel"), pid, d3)
            try:
                nivel = float(nivel)
            except (TypeError, ValueError):
                nivel = 0.0
            try:
                wt = float(water_table(nivel, d3) or 0.0)
            except (TypeError, ValueError):
                wt = 0.0

        stored = InteractionDetail.objects.filter(catchment_point_id=pid, date_time_medition=bstr).first()
        if stored:
            s_tot = None
            try:
                s_tot = int(round(float(stored.total)))
            except (TypeError, ValueError):
                pass
            s_nivel = float(stored.nivel) if stored.nivel else 0.0
            s_wt = float(stored.water_table) if stored.water_table else 0.0
            s_flow = float(stored.flow) if stored.flow else 0.0
            print(f"  {bstr} ({label}): repro total={total} flow={round(flow,2)} nivel={round(nivel,2)} wt={round(wt,2)}")
            print(f"    stored total={s_tot} flow={s_flow} nivel={s_nivel} wt={s_wt}"
                  + ("  <== COINCIDE" if (s_tot == total and abs(s_nivel - nivel) < 0.05 and abs(s_wt - wt) < 0.05 and abs(s_flow - flow) < 0.05) else "  <== DIFIERE"))
        else:
            print(f"  {bstr} ({label}): repro total={total} (sin stored)")
