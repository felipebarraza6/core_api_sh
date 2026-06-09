import django
django.setup()

from api.core.models import InteractionDetail
from api.cronjobs.telemetry.controllers.total import total_hour, total_day
from django.db import transaction

# Rango de fechas a corregir
START_DATE = "2026-05-20T00:00:00+00:00"

print("PASO 1: Identificando registros a corregir...")
records = InteractionDetail.objects.filter(
    is_error=True,
    total__isnull=False,
    date_time_medition__gte=START_DATE,
).exclude(total='').order_by('catchment_point_id', 'date_time_medition')

total_count = records.count()
print(f"Total registros con is_error=True y total valido desde {START_DATE}: {total_count}")

# Filtrar solo los que tienen TOTALIZADO success=true en variable_details
# Para no cargar todo en memoria, lo hacemos en batches
BATCH_SIZE = 500
corrected = 0
skipped_total_fail = 0
skipped_massive_jump = 0
point_ids = set()

# Procesar por punto para recalcular coherentemente
from collections import defaultdict
point_records = defaultdict(list)

for rec in records.iterator():
    vd = rec.variable_details or []
    totalizado_ok = any(v.get('type_variable') == 'TOTALIZADO' and v.get('success') for v in vd)
    
    if not totalizado_ok:
        skipped_total_fail += 1
        continue
    
    # Verificar si hay indicio de salto masivo en variable_details (metadata de total_m3)
    # Si variable_details contiene status=MASSIVE_JUMP_BLOCKED, no desmarcar
    has_massive_jump = any(
        v.get('type_variable') == 'TOTALIZADO' and 
        isinstance(v.get('metadata'), dict) and 
        v.get('metadata', {}).get('status') == 'MASSIVE_JUMP_BLOCKED'
        for v in vd
    )
    
    if has_massive_jump:
        skipped_massive_jump += 1
        continue
    
    point_records[rec.catchment_point_id].append(rec)
    corrected += 1

print(f"  - Corregibles: {corrected}")
print(f"  - Saltados (total fail): {skipped_total_fail}")
print(f"  - Saltados (salto masivo): {skipped_massive_jump}")
print(f"  - Puntos afectados: {len(point_ids)}")

print("\nPASO 2: Desmarcando is_error...")
for point_id, recs in point_records.items():
    for rec in recs:
        rec.is_error = False
        rec.save(update_fields=['is_error'])
    print(f"  Punto {point_id}: {len(recs)} registros desmarcados")

print("\nPASO 3: Recalculando total_diff y total_today_diff por punto...")
for point_id in point_records.keys():
    all_records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=START_DATE,
    ).exclude(total__isnull=True).exclude(total='').order_by('date_time_medition')
    
    point_catchment = {"id": point_id}
    changed = 0
    
    for rec in all_records:
        total_val = float(rec.total) if rec.total else 0
        new_diff = total_hour(total_val, point_catchment, rec.date_time_medition)
        new_today = total_day(point_catchment, rec.date_time_medition, total_val)
        
        if rec.total_diff != new_diff or rec.total_today_diff != new_today:
            rec.total_diff = new_diff
            rec.total_today_diff = new_today
            rec.save(update_fields=['total_diff', 'total_today_diff'])
            changed += 1
    
    if changed > 0:
        print(f"  Punto {point_id}: {changed} registros recalculados")

print("\nListo.")
