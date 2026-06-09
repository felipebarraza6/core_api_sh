import django
django.setup()

from api.core.models import InteractionDetail, CounterResetLog
from api.cronjobs.telemetry.controllers.total import total_hour, total_day
from django.db import transaction
import logging
import time

# Silenciar logs de warnings para no llenar la salida
logging.getLogger('cronjobs.telemetry').setLevel(logging.ERROR)

START_DATE = "2026-01-01T00:00:00+00:00"

print("=" * 60)
print("VALIDACION MASIVA 2026")
print("=" * 60)

t0 = time.time()

# 1. Identificar registros a corregir
print("\n[1/4] Identificando registros con is_error=True donde TOTALIZADO llego bien...")
records = InteractionDetail.objects.filter(
    is_error=True,
    total__isnull=False,
    date_time_medition__gte=START_DATE,
).exclude(total='').order_by('catchment_point_id', 'date_time_medition')

total_error = records.count()
print(f"  Total registros con error en 2026: {total_error}")

from collections import defaultdict
point_records = defaultdict(list)
point_date_ranges = defaultdict(lambda: [None, None])  # [min_dt, max_dt]
skipped_total_fail = 0
skipped_massive_jump = 0

for rec in records.iterator():
    vd = rec.variable_details or []
    totalizado_ok = any(v.get('type_variable') == 'TOTALIZADO' and v.get('success') for v in vd)
    
    if not totalizado_ok:
        skipped_total_fail += 1
        continue
    
    # Detectar salto masivo en metadata
    has_massive_jump = False
    for v in vd:
        if v.get('type_variable') == 'TOTALIZADO':
            meta = v.get('metadata')
            if isinstance(meta, dict) and meta.get('status') == 'MASSIVE_JUMP_BLOCKED':
                has_massive_jump = True
                break
    
    # Fallback: el sistema unificado NO guarda metadata en variable_details.
    # Consultar CounterResetLog para detectar bloqueos por salto masivo.
    if not has_massive_jump:
        has_massive_jump = CounterResetLog.objects.filter(
            point_catchment_id=rec.catchment_point_id,
            date_time_medition=rec.date_time_medition,
            reset_type='MASSIVE_JUMP',
        ).exists()

    if has_massive_jump:
        skipped_massive_jump += 1
        continue
    
    pid = rec.catchment_point_id
    point_records[pid].append(rec)
    dt = rec.date_time_medition
    if point_date_ranges[pid][0] is None or dt < point_date_ranges[pid][0]:
        point_date_ranges[pid][0] = dt
    if point_date_ranges[pid][1] is None or dt > point_date_ranges[pid][1]:
        point_date_ranges[pid][1] = dt

corrected_count = sum(len(v) for v in point_records.values())
print(f"  Corregibles: {corrected_count}")
print(f"  Saltados (totalizado fallido): {skipped_total_fail}")
print(f"  Saltados (salto masivo): {skipped_massive_jump}")
print(f"  Puntos afectados: {len(point_records)}")

if corrected_count == 0:
    print("\nNada que corregir. Fin.")
    exit(0)

# 2. Desmarcar is_error
print("\n[2/4] Desmarcando is_error...")
for point_id, recs in point_records.items():
    ids = [r.id for r in recs]
    # Hacerlo en batches de 500 para no saturar
    BATCH = 500
    for i in range(0, len(ids), BATCH):
        batch = ids[i:i+BATCH]
        InteractionDetail.objects.filter(id__in=batch).update(is_error=False)
    print(f"  Punto {point_id}: {len(recs)} registros desmarcados")

# 3. Recalcular totales por punto
print("\n[3/4] Recalculando total_diff y total_today_diff...")
for idx, point_id in enumerate(point_date_ranges.keys(), 1):
    min_dt, max_dt = point_date_ranges[point_id]
    
    # Tomar un margen de 1 dia antes y despues para que los calculos sean coherentes
    from datetime import timedelta
    q_start = min_dt - timedelta(days=1)
    q_end = max_dt + timedelta(days=1)
    
    all_records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=q_start,
        date_time_medition__lte=q_end,
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
            print(f"    Error punto {point_id} id={rec.id}: {e}")
            continue
    
    if changed > 0:
        print(f"  [{idx}/{len(point_records)}] Punto {point_id}: {changed} registros recalculados ({q_start.date()} a {q_end.date()})")
    else:
        print(f"  [{idx}/{len(point_records)}] Punto {point_id}: sin cambios")

t1 = time.time()
print("\n" + "=" * 60)
print(f"LISTO. Tiempo: {t1-t0:.1f}s")
print(f"Registros desmarcados: {corrected_count}")
print("=" * 60)
