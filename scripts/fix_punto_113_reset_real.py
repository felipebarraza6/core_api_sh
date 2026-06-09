#!/usr/bin/env python3
"""
Corrección manual para Punto 113 (Nueva Energia P2) — Reset real de contador Novus.

Contexto:
- 2026-05-04 22:00 UTC: último registro pre-reset (pulses=91755, total=361651)
- 2026-05-04 23:00 UTC: primer registro post-reset (pulses=148, total=1.48)
- Los meses anteriores a mayo están corruptos (reset de junio 2025 no compensado,
  addition mal calculado). Por eso addition=0: solo se considera el consumo
  desde el reset de mayo.
- DGA no se ve afectado porque envía total_sin_offset (valor crudo del logger).

Acciones:
1. Actualiza ProfileDataConfigCatchment.addition = 0
2. Reprocesa total para todos los registros post-reset (2026-05-04 23:00 en adelante)
3. Recalcula total_diff y total_today_diff para todo el período afectado

Uso (ya aplicado en producción 2026-05-18):
    docker exec -u root -w /app django_api_secure python scripts/fix_punto_113_reset_real.py
"""

import os
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django

django.setup()

from django.utils import timezone
import pytz
from decimal import Decimal
from api.core.models import InteractionDetail, ProfileDataConfigCatchment


def main():
    pid = 113
    new_addition = Decimal("0")
    factor = Decimal("10")
    utc = pytz.UTC

    # 1. Actualizar addition del perfil
    profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=pid).first()
    if not profile:
        print("❌ Perfil no encontrado")
        return

    print(f"PROFILE: addition {profile.addition} → {new_addition}")
    profile.addition = new_addition
    profile.save(update_fields=["addition"])

    # 2. Reprocesar totales desde el reset
    dt_start = utc.localize(timezone.datetime(2026, 5, 4, 23, 0, 0))
    regs = list(
        InteractionDetail.objects.filter(
            catchment_point_id=pid, date_time_medition__gte=dt_start
        ).order_by("date_time_medition")
    )
    print(f"Registros post-reset a reprocesar: {len(regs)}")

    for r in regs:
        raw = (Decimal(str(r.pulses)) * factor) / Decimal("1000")
        new_total_float = float(raw)

        # Formato: entero si no tiene decimales, 2 decimales si sí
        if new_total_float == int(new_total_float):
            new_total_str = str(int(new_total_float))
        else:
            new_total_str = f"{new_total_float:.2f}"

        if r.total != new_total_str:
            r.total = new_total_str
            r.save(update_fields=["total"])

    # 3. Recalcular diffs incluyendo el pre-reset como base
    dt_base = utc.localize(timezone.datetime(2026, 5, 4, 22, 0, 0))
    all_regs = list(
        InteractionDetail.objects.filter(
            catchment_point_id=pid, date_time_medition__gte=dt_base
        ).order_by("date_time_medition")
    )
    print(f"Registros para recalcular diffs: {len(all_regs)}")

    first_total_of_day = {}
    prev_total = None

    for i, r in enumerate(all_regs):
        curr_total = float(r.total)
        day = r.date_time_medition.date()

        if day not in first_total_of_day:
            first_total_of_day[day] = curr_total

        if i == 0:
            diff = 0
            today_diff = 0
        else:
            diff = max(0, int(round(curr_total - prev_total)))
            today_diff = max(0, int(round(curr_total - first_total_of_day[day])))

        if r.total_diff != diff or r.total_today_diff != today_diff:
            r.total_diff = diff
            r.total_today_diff = today_diff
            r.save(update_fields=["total_diff", "total_today_diff"])

        prev_total = curr_total

    # Verificación
    last = InteractionDetail.objects.filter(catchment_point_id=pid).order_by(
        "-date_time_medition"
    ).first()
    print(
        f"✅ Ultimo registro: {last.date_time_medition} total={last.total} "
        f"diff={last.total_diff} today_diff={last.total_today_diff}"
    )


if __name__ == "__main__":
    main()
