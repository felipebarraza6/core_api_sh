import django
django.setup()

from api.core.models import InteractionDetail
from api.cronjobs.telemetry.controllers.total import total_hour, total_day
import logging
logging.getLogger('cronjobs.telemetry').setLevel(logging.ERROR)

START_DATE = "2026-05-24T00:00:00+00:00"

print("PASO 1: Identificando registros a corregir...")
records = InteractionDetail.objects.filter(
    is_error=True,
    total__isnull=False,
    date_time_medition__gte=START_DATE,
).exclude(total='').order_by('catchment_point_id', 'date_time_medition')

from collections import defaultdict
point_records = defaultdict(list)
skipped_total_fail = 0

for rec in records.iterator():
    vd = rec.variable_details or []
    totalizado_ok = any(v.get('type_variable') == 'TOTALIZADO' and v.get('success') for v in vd)
    
    if not totalizado_ok:
        skipped_total_fail += 1
        continue
    
    point_records[rec.catchment_point_id].append(rec)

print(f"  Corregibles: {sum(len(v) for v in point_records.values())}")
print(f"  Saltados (total fail): {skipped_total_fail}")
print(f"  Puntos afectados: {len(point_records)}")

print("\nPASO 2: Desmarcando is_error...")
for point_id, recs in point_records.items():
    InteractionDetail.objects.filter(id__in=[r.id for r in recs]).update(is_error=False)
    print(f"  Punto {point_id}: {len(recs)} registros desmarcados")

print("\nPASO 3: Recalculando total_diff y total_today_diff...")
for point_id in point_records.keys():
    all_records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=START_DATE,
    ).exclude(total__isnull=True).exclude(total='').order_by('date_time_medition')
    
    point_catchment = {"id": point_id}
    changed = 0
    
    for rec in all_records:
        try:
            total_val = float(rec.total) if rec.total else 0
            new_diff = total_hour(total_val, point_catchment, rec.date_time_medition)
            new_today = total_day(point_catchment, rec.date_time_medition, total_val)
            
            if rec.total_diff != new_diff or rec.total_today_diff != new_today:
                rec.total_diff = new_diff
                rec.total_today_diff = new_today
                rec.save(update_fields=['total_diff', 'total_today_diff'])
                changed += 1
        except Exception as e:
            print(f"    Error en punto {point_id} id={rec.id}: {e}")
            continue
    
    if changed > 0:
        print(f"  Punto {point_id}: {changed} registros recalculados")

print("\nListo.")
