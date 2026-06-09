#!/usr/bin/env python3
"""
Corrige registros con pulses>0 pero total='0' en mayo 2026.
Esto ocurre cuando el anti-salto bloqueó el total después de un pulses=0 falso.

ESTRATEGIA CONSERVADORA:
1. Solo toca registros donde total='0' o total=None Y pulses>0
2. Para cada punto, itera registros de mayo en orden
3. Mantiene un running_total y running_pulses (último válido)
4. Cuando encuentra total='0' con pulses>0, recalcula:
   - diff = current_pulses - running_pulses (si no reset) o current_pulses (si reset)
   - new_total = running_total + diff * factor / 1000
5. NO toca registros donde total ya es != '0' (aunque parezca incorrecto)

Uso (simulación):
    docker exec -u root -w /app django_api_secure python scripts/fix_total_cero_post_pulsos_cero.py

Uso (aplicar):
    docker exec -u root -w /app -e FORCE_CORRECTION=1 django_api_secure python scripts/fix_total_cero_post_pulsos_cero.py
"""

import os
import sys
import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django

django.setup()

from django.db import transaction
from api.core.models import InteractionDetail, Variable, ProfileDataConfigCatchment


def log(msg):
    print(msg, flush=True)


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def main():
    start_time = datetime.now()
    force = os.environ.get("FORCE_CORRECTION", "0") == "1"

    # Mapear puntos a factor
    log("🔍 Mapeando puntos a factor...")
    point_factors = {}
    for v in Variable.objects.filter(type_variable="TOTALIZADO").select_related("scheme_catchment"):
        for p in v.scheme_catchment.points_catchment.all():
            point_factors[p.id] = v.pulses_factor or 1000
    log(f"   {len(point_factors)} puntos")

    # Backup
    backup_path = f"/app/backups/backup_fix_total_cero_post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    os.makedirs("/app/backups", exist_ok=True)

    fieldnames = [
        "id", "catchment_point_id", "date_time_medition",
        "pulses", "old_total", "new_total", "running_pulses", "running_total", "action",
    ]

    corrections = []
    skipped = 0

    for pid, factor in point_factors.items():
        may_records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte="2026-05-01",
                date_time_medition__lt="2026-06-01",
            ).order_by("date_time_medition").values(
                "id", "date_time_medition", "pulses", "total",
            )
        )
        if not may_records:
            continue

        # Buscar base pre-mayo
        prior = InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__lt="2026-05-01",
            pulses__gt=0,
        ).exclude(total__isnull=True).exclude(total="").exclude(total="0").exclude(total="None").order_by(
            "-date_time_medition"
        ).values("pulses", "total").first()

        if prior:
            running_pulses = float(prior["pulses"])
            running_total = float(prior["total"])
        else:
            # Buscar primer registro de mayo con total válido
            base = None
            for r in may_records:
                if r["pulses"] is not None and r["pulses"] > 0 and r["total"] not in (None, "", "0", "None"):
                    try:
                        float(r["total"])
                        base = r
                        break
                    except (ValueError, TypeError):
                        pass
            if base:
                running_pulses = float(base["pulses"])
                running_total = float(base["total"])
            else:
                # Todo es 0 o None, no podemos hacer nada sin base
                # Intentar con addition
                profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=pid).first()
                addition = float(profile.addition) if profile and profile.addition else 0.0
                first_pulse = None
                for r in may_records:
                    if r["pulses"] is not None and r["pulses"] > 0:
                        first_pulse = r
                        break
                if first_pulse:
                    running_pulses = float(first_pulse["pulses"])
                    running_total = (running_pulses * factor) / 1000.0 + addition
                else:
                    continue

        for r in may_records:
            rid = r["id"]
            current_pulses = r["pulses"]
            old_total = r["total"]

            is_bad = (old_total in (None, "", "0", "None")) and (current_pulses is not None and current_pulses > 0)

            if is_bad:
                cp = float(current_pulses)
                if cp >= running_pulses:
                    diff = cp - running_pulses
                else:
                    diff = cp  # reset
                new_total = running_total + (diff * factor) / 1000.0
                new_total_rounded = round_total(new_total)

                # Solo corregir si el nuevo total realmente difiere del viejo
                old_total_rounded = round_total(float(old_total)) if old_total not in (None, "", "None") else 0
                if new_total_rounded != old_total_rounded:
                    corrections.append({
                        "id": rid,
                        "catchment_point_id": pid,
                        "date_time_medition": r["date_time_medition"].strftime("%Y-%m-%d %H:%M:%S"),
                        "pulses": current_pulses,
                        "old_total": old_total,
                        "new_total": str(new_total_rounded),
                        "running_pulses": running_pulses,
                        "running_total": running_total,
                        "action": "CORRECT",
                    })
                # Actualizar running para siguientes registros
                running_pulses = cp
                running_total = new_total
            else:
                # Registro válido, actualizar running
                if current_pulses is not None and current_pulses > 0:
                    try:
                        t = float(old_total) if old_total not in (None, "", "None") else 0.0
                        running_pulses = float(current_pulses)
                        running_total = t
                    except (ValueError, TypeError):
                        pass
                skipped += 1

    log(f"📊 Correcciones necesarias: {len(corrections)}")
    log(f"   Registros válidos skipped: {skipped}")

    if not corrections:
        log("✅ No hay correcciones necesarias.")
        return

    # Guardar backup CSV
    with open(backup_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(corrections)
    log(f"💾 Backup/simulación guardado en: {backup_path}")

    log("\n📝 Muestra de correcciones:")
    for r in corrections[:10]:
        log(f"   Punto {r['catchment_point_id']} @ {r['date_time_medition']}: "
            f"pulses={r['pulses']} total {repr(r['old_total'])} → {r['new_total']}")

    if not force:
        log("\n⚠️  Para aplicar, re-ejecuta con FORCE_CORRECTION=1")
        return

    # Aplicar
    log(f"\n🔧 Aplicando {len(corrections)} correcciones...")
    updated = 0
    errors = 0
    with transaction.atomic():
        for r in corrections:
            try:
                InteractionDetail.objects.filter(id=r["id"]).update(total=r["new_total"])
                updated += 1
                if updated % 500 == 0:
                    log(f"   ... {updated} actualizados")
            except Exception as e:
                log(f"   ❌ Error en id={r['id']}: {e}")
                errors += 1

    log(f"\n✅ Listo!")
    log(f"   Actualizados: {updated}")
    log(f"   Errores: {errors}")
    log(f"   Backup: {backup_path}")
    log(f"   Tiempo: {datetime.now() - start_time}")


if __name__ == "__main__":
    main()
