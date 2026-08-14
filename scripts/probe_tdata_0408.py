#!/usr/bin/env python3
"""Probe: ¿el histórico TDATA tiene el bucket 2026-08-04 19:00 UTC para los 21 puntos DGA afectados?"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from api.core.models import CatchmentPoint, SchemesCatchment, Variable
from api.cronjobs.telemetry.getters.tdata import get_data_tdata_history

UTC = None
import pytz
UTC = pytz.utc
CHILE = pytz.timezone("America/Santiago")

POINTS = [149, 156, 157, 158, 159, 160, 161, 163, 167, 172, 175,
          184, 186, 203, 204, 209, 210, 211]

# Ventana amplia alrededor del bucket objetivo: 19:00 UTC (15:00 CLT)
START = datetime(2026, 8, 4, 17, 0, 0, tzinfo=UTC)
END = datetime(2026, 8, 4, 21, 0, 0, tzinfo=UTC)
# TDATA interpreta datetimes como CLT wall-clock (quirk del getter)
TDATA_START = datetime(2026, 8, 4, 13, 0, 0)
TDATA_END = datetime(2026, 8, 4, 17, 0, 0)

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
    print(f"=== PUNTO {pid} ({pt.title}) provider={provider.handler_name} d3={profile.d3} addition={profile.addition}")
    for v in vars_db:
        if (v.type_variable or "").upper() == "CAUDAL_PROMEDIO":
            continue
        token = v.token_service or ptoken
        hist = get_data_tdata_history(provider, token, v.str_variable, TDATA_START, TDATA_END, limit=10000)
        in_window = [h for h in hist if datetime.strptime(h["date_time"], "%Y-%m-%dT%H:%M:%S").hour in (14, 15, 16)]
        print(f"  var {v.type_variable or '?'} str={v.str_variable} hist={len(hist)} "
              f"en_14-16h={len(in_window)} {in_window[:2]}")
