#!/usr/bin/env python3
"""
AUDITORÍA DGA GLOBAL — Agosto 2026 (clasifica registros existentes con validate_frequency).

Replica EXACTAMENTE la lógica del cron (unified_processing.validate_frequency) sobre los
REGISTROS EXISTENTES de cada punto DGA (send_dga=True en config) en la ventana
[2026-08-01, ahora]:

  - LAGUNA DE VOUCHER: registro que SEGÚN STANDARD debe enviarse pero está con
    send_dga=False, sin is_error y sin n_voucher válido (nunca se encoló ni envió).
  - EN COLA:           debe enviarse y send_dga=True (se enviará en próximos ciclos).
  - CON ERROR:         debe enviarse pero is_error=True (falló, revisar retry).
  - LAGUNA DE DATO:    slot horario sin ningún registro que deba enviarse.
    Para freq=60 -> 1 slot/hora (:00 CLT). Para freq<60 -> 1 slot/hora (registro con
    minute<freq, desalineación del cron tolerada). Estándares con condición de día/mes
    (MEDIO/MENOR/CAUDALES_MUY_PEQUENOS) solo generan slots en las fechas que califican.

Registros que NO califican según standard NO son lagunas por diseño (p.ej. buckets 5-min
con minute>=freq, o agosto para CAUDALES_MUY_PEQUENOS).

Uso:
  python audit_dga_global.py                 # reporte completo
  python audit_dga_global.py --points 12,14
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from collections import OrderedDict

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail

CHILE = pytz.timezone("America/Santiago")
UTC = pytz.utc

WINDOW_START = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
WINDOW_END = datetime.utcnow().replace(tzinfo=UTC)


def qualifies(standard, dt_clt, freq):
    """Replica validate_frequency sobre un datetime CLT naive."""
    if standard == "MAYOR":
        if freq == 60:
            return dt_clt.minute == 0
        return dt_clt.minute < freq
    if standard == "MEDIO":
        if freq == 60:
            return dt_clt.hour == 0 and dt_clt.minute == 0
        return dt_clt.hour == 0 and dt_clt.minute < freq
    if standard == "MENOR":
        if freq == 60:
            return dt_clt.day == 1 and dt_clt.hour == 0 and dt_clt.minute == 0
        return dt_clt.day == 1 and dt_clt.hour == 0 and dt_clt.minute < freq
    if standard == "CAUDALES_MUY_PEQUENOS":
        if freq == 60:
            return dt_clt.month in (1, 7) and dt_clt.day == 1 and dt_clt.hour == 0 and dt_clt.minute == 0
        return dt_clt.month in (1, 7) and dt_clt.day == 1 and dt_clt.hour == 0 and dt_clt.minute < freq
    if standard == "SIN_ESTANDAR":
        if freq == 60:
            return dt_clt.minute == 0
        return dt_clt.minute < freq
    return False


def slot_keys(standard, start_clt, end_clt, freq):
    """Conjunto de (fecha, hora) CLT que DEBEN tener un envío en la ventana."""
    slots = set()
    t = start_clt
    if freq >= 60:
        # recorrer cada hora
        t = t.replace(minute=0, second=0, microsecond=0)
        while t < end_clt:
            if qualifies(standard, t, 60):
                slots.add(t.replace(minute=0, second=0, microsecond=0))
            t += timedelta(hours=1)
    else:
        # recorrer cada hora verificando minute<freq (desalineación tolerada)
        t = t.replace(minute=0, second=0, microsecond=0)
        while t < end_clt:
            if qualifies(standard, t, freq):
                slots.add(t.replace(minute=0, second=0, microsecond=0))
            t += timedelta(hours=1)
    return slots


def audit_point(pid):
    cfg = DgaDataConfigCatchment.objects.get(point_catchment_id=pid)
    pt = cfg.point_catchment
    freq = int(pt.frecuency) if pt.frecuency else 60
    standard = cfg.standard

    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gte=WINDOW_START,
            date_time_medition__lt=WINDOW_END,
        ).order_by("date_time_medition")
        .values_list("date_time_medition", "n_voucher", "send_dga", "is_error", "dga_retry_count")
    )

    # Clasificar registros existentes
    ok = en_cola = lv = con_error = 0
    lv_samples = []
    ce_samples = []
    sent_slots = set()   # slots con envío válido (voucher)
    ok_slots = set()

    for ts, n_voucher, send_dga, is_error, retry in records:
        dt_clt = ts.astimezone(CHILE).replace(tzinfo=None)
        if not qualifies(standard, dt_clt, freq):
            continue
        slot = dt_clt.replace(minute=0, second=0, microsecond=0)
        has_voucher = bool(n_voucher) and n_voucher not in ("", "None", "No se pudo obtener el comprobante")
        if is_error:
            con_error += 1
            sent_slots.add(slot)
            if len(ce_samples) < 3:
                ce_samples.append(ts)
        elif send_dga:
            en_cola += 1
            sent_slots.add(slot)
        elif has_voucher:
            ok += 1
            ok_slots.add(slot)
        else:
            lv += 1
            sent_slots.add(slot)
            if len(lv_samples) < 3:
                lv_samples.append(ts)

    # Slots esperados sin ningún envío válido
    start_clt = WINDOW_START.astimezone(CHILE).replace(tzinfo=None)
    end_clt = WINDOW_END.astimezone(CHILE).replace(tzinfo=None)
    expected = slot_keys(standard, start_clt, end_clt, freq)
    all_sent = sent_slots | ok_slots
    laguna_dato = sorted(expected - all_sent)
    ld_samples = [CHILE.localize(s).astimezone(UTC) for s in laguna_dato[:3]]

    return {
        "pid": pid, "title": pt.title, "freq": freq, "standard": standard,
        "start_compliance": cfg.date_start_compliance,
        "esperados": len(expected),
        "ok": ok, "en_cola": en_cola, "lv": lv, "ld": len(laguna_dato), "err": con_error,
        "lv_samples": lv_samples, "ld_samples": ld_samples, "ce_samples": ce_samples,
    }


def main():
    ap = argparse.ArgumentParser(description="Auditoría DGA global agosto 2026")
    ap.add_argument("--points", default=None)
    args = ap.parse_args()

    if args.points:
        pids = [int(x) for x in args.points.split(",")]
    else:
        pids = list(
            DgaDataConfigCatchment.objects.filter(send_dga=True)
            .order_by("point_catchment_id")
            .values_list("point_catchment_id", flat=True)
        )

    rows = []
    for pid in pids:
        try:
            rows.append(audit_point(pid))
        except DgaDataConfigCatchment.DoesNotExist:
            print(f"  !!! punto {pid}: sin config DGA")
        except Exception as e:
            print(f"  !!! punto {pid}: error {e}")

    rows.sort(key=lambda r: (r["standard"], r["pid"]))

    print(f"{'pt':<5}{'freq':<5}{'standard':<22}{'esp':>5}{'ok':>5}{'cola':>5}{'lv':>5}{'ld':>5}{'err':>5}  detalle")
    print("-" * 120)
    tot = {"esperados": 0, "ok": 0, "en_cola": 0, "lv": 0, "ld": 0, "err": 0}
    for r in rows:
        tot["esperados"] += r["esperados"]
        tot["ok"] += r["ok"]
        tot["en_cola"] += r["en_cola"]
        tot["lv"] += r["lv"]
        tot["ld"] += r["ld"]
        tot["err"] += r["err"]
        det = ""
        if r["lv_samples"]:
            det += " LV:" + ",".join(x.strftime("%d%H%M") for x in r["lv_samples"])
        if r["ld_samples"]:
            det += " LD:" + ",".join(x.strftime("%d%H") for x in r["ld_samples"])
        if r["ce_samples"]:
            det += " ERR:" + ",".join(x.strftime("%d%H") for x in r["ce_samples"])
        print(f"{r['pid']:<5}{r['freq']:<5}{r['standard']:<22}"
              f"{r['esperados']:>5}{r['ok']:>5}{r['en_cola']:>5}"
              f"{r['lv']:>5}{r['ld']:>5}{r['err']:>5}  {det}")
    print("-" * 120)
    print(f"TOTALES: esperados={tot['esperados']} con_voucher={tot['ok']} en_cola={tot['en_cola']} "
          f"LAGUNA_VOUCHER={tot['lv']} LAGUNA_DATO={tot['ld']} con_error={tot['err']}")


if __name__ == "__main__":
    main()
