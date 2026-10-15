#!/usr/bin/env python3
"""
Re-encola envíos DGA perdidos (lagunas reales detectadas por audit_dga_global).

Lotes:
  A) 2026-09-01 22:00-23:00 CLT — servidor DGA caído (agotó 5 reintentos).
  B) 2026-08-14 15:00-23:00 CLT — deploy sin migración 0084 (send_dga=False al crearse).
  C) Punto 130 — reportes mensuales (1-ago, 1-sep, 1-oct) nunca encolados.

Uso:
  python scripts/requeue_dga_gaps.py            # dry-run (solo reporta)
  python scripts/requeue_dga_gaps.py --apply    # marca send_dga=True para reenvío

Precaución: solo toca InteractionDetail (send_dga/is_error/dga_retry_count),
nunca modelos ni migraciones. Verificado con un registro de prueba previo.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz
from django.utils import timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit_dga_global import CHILE, UTC, qualifies, is_local_time_valid  # noqa: E402
from api.core.models import InteractionDetail, DgaDataConfigCatchment  # noqa: E402

MSG_SERVIDOR_CAIIDO = (
    "Error: El servidor DGA no está respondiendo tras todos los intentos persistentes."
)

APPLY = "--apply" in sys.argv


def active_dga_points():
    return set(
        DgaDataConfigCatchment.objects.filter(send_dga=True)
        .values_list("point_catchment_id", flat=True)
    )


def reset(qs):
    """Marca los registros del queryset para reenvío."""
    if APPLY:
        return qs.update(
            send_dga=True,
            is_error=False,
            dga_retry_count=0,
            dga_last_retry_at=None,
        )
    return qs.count()


def main():
    pids = active_dga_points() - {1}  # cron_dga excluye punto 1 (reporta vía SMA)
    base = InteractionDetail.objects.filter(catchment_point_id__in=pids)

    # ---- Lote A: errores 1-sep (servidor caído) -------------------------
    a = base.filter(
        is_error=True,
        send_dga=False,
        return_dga=MSG_SERVIDOR_CAIIDO,
    )
    n_a = reset(a)

    # ---- Lote B: ventana 14-ago 15:00-23:00 CLT ------------------------
    ini = CHILE.localize(datetime(2026, 8, 14, 15, 0, 0)).astimezone(UTC)
    fin = CHILE.localize(datetime(2026, 8, 14, 23, 59, 59)).astimezone(UTC)
    candidatos_b = base.filter(
        date_time_medition__gte=ini,
        date_time_medition__lte=fin,
        send_dga=False,
        is_error=False,
    ).filter(n_voucher__isnull=True).select_related("catchment_point")

    ids_b = []
    for r in candidatos_b:
        cfg = (
            DgaDataConfigCatchment.objects.filter(
                point_catchment_id=r.catchment_point_id
            )
            .order_by("-send_dga", "-id")
            .first()
        )
        if cfg is None:
            continue
        dt_clt = r.date_time_medition.astimezone(CHILE).replace(tzinfo=None)
        if is_local_time_valid(dt_clt) and qualifies(cfg.standard, dt_clt, int(r.catchment_point.frecuency or 60)):
            ids_b.append(r.id)
    b = InteractionDetail.objects.filter(id__in=ids_b)
    n_b = reset(b)

    # ---- Lote C: pt 130 mensuales --------------------------------------
    c = []
    for mes, dia in ((8, 1), (9, 1), (10, 1)):
        h_ini = CHILE.localize(datetime(2026, mes, dia, 0, 0, 0)).astimezone(UTC)
        h_fin = CHILE.localize(datetime(2026, mes, dia, 0, 59, 59)).astimezone(UTC)
        c.append(
            base.filter(
                catchment_point_id=130,
                date_time_medition__gte=h_ini,
                date_time_medition__lte=h_fin,
                send_dga=False,
                is_error=False,
            ).filter(n_voucher__isnull=True)
        )
    n_c = sum(reset(x) for x in c)

    modo = "APLICADO" if APPLY else "DRY-RUN"
    print(f"[{modo}] A(1-sep servidor caído)={n_a}  B(14-ago 15-23h)={n_b}  C(pt130 mensual)={n_c}")
    if not APPLY:
        print("Ejecuta con --apply para re-encolar.")


if __name__ == "__main__":
    main()
