#!/usr/bin/env python3
"""
Recálculo en cascada de totales para puntos TOTALIZADO en mayo 2026.

CORRIGE:
- Registros pulses=0 con total incorrecto (manteniendo pulses=0, total congelado)
- Registros pulses>0 con total=0 por anti-salto bloqueado después de pulses=0 falsos
- Incoherencias en total_diff y total_today_diff

ESTRATEGIA:
1. Para cada punto, encontrar base válida pre-mayo (o primer registro de mayo)
2. Iterar registros de mayo en orden cronológico
3. Calcular total en cascada: new_total = last_total + diff * factor / 1000
4. diff = current_pulses - last_real_pulses (si no hay reset) o current_pulses (si reset)
5. pulses=0 → total congelado al último válido
6. Segunda pasada: recalcular total_diff y total_today_diff

Uso (simulación):
    docker exec -u root -w /app django_api_secure python scripts/recalcular_totales_mayo_cascada.py

Uso (aplicar):
    docker exec -u root -w /app -e FORCE_CORRECTION=1 django_api_secure python scripts/recalcular_totales_mayo_cascada.py
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
from api.core.models import InteractionDetail, Variable, CatchmentPoint, ProfileDataConfigCatchment


def log(msg):
    print(msg, flush=True)


def round_total(val):
    """Redondea como lo hace total_m3: int(round(val))"""
    return int(Decimal(str(val)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def main():
    start_time = datetime.now()
    force = os.environ.get("FORCE_CORRECTION", "0") == "1"

    # 1. Mapear puntos a factor
    log("🔍 Mapeando puntos a factor de pulsos...")
    point_factors = {}
    for v in Variable.objects.filter(type_variable="TOTALIZADO").select_related("scheme_catchment"):
        for p in v.scheme_catchment.points_catchment.all():
            point_factors[p.id] = v.pulses_factor or 1000
    log(f"   {len(point_factors)} puntos mapeados")

    # 2. Backup y análisis
    backup_path = f"/app/backups/backup_recalculo_mayo_antes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    os.makedirs("/app/backups", exist_ok=True)
    log(f"💾 Backup será creado en: {backup_path}")

    fieldnames = [
        "id", "catchment_point_id", "date_time_medition",
        "pulses", "old_total", "new_total", "old_diff", "new_diff",
        "old_today_diff", "new_today_diff", "action",
    ]

    total_corrections = 0
    total_diff_corrections = 0
    total_today_corrections = 0
    rows = []

    for pid, factor in point_factors.items():
        # Obtener TODOS los registros del punto en mayo
        may_records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte="2026-05-01",
                date_time_medition__lt="2026-06-01",
            ).order_by("date_time_medition").values(
                "id", "date_time_medition", "pulses", "total",
                "total_diff", "total_today_diff",
            )
        )
        if not may_records:
            continue

        # Encontrar base pre-mayo
        prior = InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__lt="2026-05-01",
            pulses__gt=0,
        ).exclude(total__isnull=True).exclude(total="").exclude(total="0").exclude(total="None").order_by(
            "-date_time_medition"
        ).values("pulses", "total").first()

        if prior:
            last_real_pulses = float(prior["pulses"])
            last_total = float(prior["total"])
        else:
            # Sin base pre-mayo: usar primer registro de mayo con pulses>0 y total válido
            first_valid = None
            for r in may_records:
                if r["pulses"] is not None and r["pulses"] > 0 and r["total"] not in (None, "", "0", "None"):
                    try:
                        float(r["total"])
                        first_valid = r
                        break
                    except (ValueError, TypeError):
                        pass
            if first_valid:
                last_real_pulses = float(first_valid["pulses"])
                last_total = float(first_valid["total"])
                # Este primer registro se considera base, no se recalcula su total
            else:
                # No hay base válida en absoluto para este punto en mayo
                # Intentar con addition del perfil
                profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=pid).first()
                addition = float(profile.addition) if profile and profile.addition else 0.0
                # Buscar primer registro con pulses>0
                first_pulse = None
                for r in may_records:
                    if r["pulses"] is not None and r["pulses"] > 0:
                        first_pulse = r
                        break
                if first_pulse:
                    last_real_pulses = float(first_pulse["pulses"])
                    last_total = (last_real_pulses * factor) / 1000.0 + addition
                else:
                    # Todo el mes es pulses=0, nada que hacer
                    continue

        # Iterar y calcular en cascada
        calculated = {}  # id -> new_total
        for r in may_records:
            rid = r["id"]
            current_pulses = r["pulses"]
            old_total_str = r["total"]

            if current_pulses is None:
                # No debería pasar, pero por seguridad
                new_total = last_total
            elif current_pulses == 0:
                # Congelar total
                new_total = last_total
            else:
                # Calcular diff desde last_real_pulses
                cp = float(current_pulses)
                if cp >= last_real_pulses:
                    diff = cp - last_real_pulses
                else:
                    # Reset detectado
                    diff = cp
                new_total = last_total + (diff * factor) / 1000.0
                last_real_pulses = cp

            calculated[rid] = new_total
            last_total = new_total

        # Ahora verificar qué registros necesitan actualización de total
        for r in may_records:
            rid = r["id"]
            new_total = calculated[rid]
            old_total_str = r["total"]

            try:
                old_total = float(old_total_str) if old_total_str not in (None, "", "None") else 0.0
            except (ValueError, TypeError):
                old_total = 0.0

            new_total_rounded = round_total(new_total)
            old_total_rounded = round_total(old_total)

            if new_total_rounded != old_total_rounded:
                total_corrections += 1
                action = f"CORRECT_TOTAL_{old_total_rounded}_{new_total_rounded}"
            else:
                action = "KEEP_TOTAL"

            rows.append({
                "id": rid,
                "catchment_point_id": pid,
                "date_time_medition": r["date_time_medition"].strftime("%Y-%m-%d %H:%M:%S"),
                "pulses": r["pulses"],
                "old_total": old_total_str,
                "new_total": str(new_total_rounded),
                "old_diff": r["total_diff"],
                "new_diff": None,  # se calcula después
                "old_today_diff": r["total_today_diff"],
                "new_today_diff": None,
                "action": action,
            })

    log(f"📊 Correcciones de total necesarias: {total_corrections} de {len(rows)} registros")

    if total_corrections == 0:
        log("✅ No hay correcciones de total necesarias.")
        return

    # Muestra
    sample = [r for r in rows if r["action"].startswith("CORRECT")][:10]
    log("\n📝 Muestra de correcciones de total:")
    for r in sample:
        log(f"   Punto {r['catchment_point_id']} @ {r['date_time_medition']}: "
            f"total {repr(r['old_total'])} → {r['new_total']}")

    if not force:
        log("\n⚠️  Para aplicar correcciones de total, re-ejecuta con FORCE_CORRECTION=1")
        # Guardar backup CSV igual para revisión
        with open(backup_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        log(f"   Simulación guardada en: {backup_path}")
        return

    # 3. Aplicar correcciones de total
    log(f"\n🔧 Aplicando {total_corrections} correcciones de total...")
    updated = 0
    errors = 0
    with transaction.atomic():
        for r in rows:
            if not r["action"].startswith("CORRECT"):
                continue
            try:
                InteractionDetail.objects.filter(id=r["id"]).update(total=str(r["new_total"]))
                updated += 1
                if updated % 500 == 0:
                    log(f"   ... {updated} actualizados")
            except Exception as e:
                log(f"   ❌ Error en id={r['id']}: {e}")
                errors += 1

    log(f"   Total actualizados: {updated}, errores: {errors}")

    # 4. Recalcular total_diff y total_today_diff en segunda pasada
    log("\n🔄 Recalculando total_diff y total_today_diff...")
    diff_updates = 0
    today_diff_updates = 0

    for pid in point_factors.keys():
        may_records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte="2026-05-01",
                date_time_medition__lt="2026-06-01",
            ).order_by("date_time_medition").values(
                "id", "date_time_medition", "total", "total_diff", "total_today_diff"
            )
        )
        if not may_records:
            continue

        # Obtener total anterior pre-mayo
        prior = InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__lt="2026-05-01",
        ).exclude(total__isnull=True).exclude(total="").exclude(total="0").exclude(total="None").order_by(
            "-date_time_medition"
        ).values("total").first()

        prev_total = float(prior["total"]) if prior else 0.0

        # Mapa de primer total del día
        first_total_of_day = {}
        for r in may_records:
            day = r["date_time_medition"].date()
            if day not in first_total_of_day:
                try:
                    first_total_of_day[day] = float(r["total"]) if r["total"] not in (None, "", "None") else 0.0
                except (ValueError, TypeError):
                    first_total_of_day[day] = 0.0

        for r in may_records:
            rid = r["id"]
            try:
                curr_total = float(r["total"]) if r["total"] not in (None, "", "None") else 0.0
            except (ValueError, TypeError):
                curr_total = 0.0

            # total_diff
            new_diff = max(0, round_total(curr_total) - round_total(prev_total))
            old_diff = r["total_diff"] or 0
            if new_diff != old_diff:
                try:
                    InteractionDetail.objects.filter(id=rid).update(total_diff=new_diff)
                    diff_updates += 1
                except Exception as e:
                    log(f"   ❌ Error diff id={rid}: {e}")

            # total_today_diff
            day = r["date_time_medition"].date()
            first_total = first_total_of_day.get(day, 0.0)
            new_today_diff = max(0, round_total(curr_total) - round_total(first_total))
            old_today_diff = r["total_today_diff"] or 0
            if new_today_diff != old_today_diff:
                try:
                    InteractionDetail.objects.filter(id=rid).update(total_today_diff=new_today_diff)
                    today_diff_updates += 1
                except Exception as e:
                    log(f"   ❌ Error today_diff id={rid}: {e}")

            prev_total = curr_total

    log(f"   total_diff actualizados: {diff_updates}")
    log(f"   total_today_diff actualizados: {today_diff_updates}")

    log(f"\n✅ Recálculo completado!")
    log(f"   Total actualizados: {updated}")
    log(f"   diff actualizados: {diff_updates}")
    log(f"   today_diff actualizados: {today_diff_updates}")
    log(f"   Errores: {errors}")
    log(f"   Tiempo: {datetime.now() - start_time}")


if __name__ == "__main__":
    main()
