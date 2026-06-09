import django
django.setup()

from api.core.models import InteractionDetail
from api.cronjobs.telemetry.controllers.total import total_hour, total_day

point_id = 113
records = InteractionDetail.objects.filter(
    catchment_point_id=point_id,
    is_error=True,
    total__isnull=False,
    date_time_medition__date='2026-05-24'
).exclude(total='').order_by('date_time_medition')

print(f"Registros a corregir: {records.count()}")

for r in records:
    vd = r.variable_details or []
    total_ok = any(v.get('type_variable') == 'TOTALIZADO' and v.get('success') for v in vd)
    if total_ok:
        r.is_error = False
        r.save(update_fields=['is_error'])
        print(f"  Desmarcado is_error: id={r.id} {r.date_time_medition}")

print("\nRecalculando total_diff y total_today_diff...")

all_records = InteractionDetail.objects.filter(
    catchment_point_id=point_id,
    date_time_medition__date='2026-05-24'
).exclude(total__isnull=True).exclude(total='').order_by('date_time_medition')

point_catchment = {"id": point_id}

for rec in all_records:
    total_val = float(rec.total) if rec.total else 0
    new_diff = total_hour(total_val, point_catchment, rec.date_time_medition)
    new_today = total_day(point_catchment, rec.date_time_medition, total_val)
    
    if rec.total_diff != new_diff or rec.total_today_diff != new_today:
        print(f"  id={rec.id} {rec.date_time_medition}: total_diff {rec.total_diff} -> {new_diff}, today_diff {rec.total_today_diff} -> {new_today}")
        rec.total_diff = new_diff
        rec.total_today_diff = new_today
        rec.save(update_fields=['total_diff', 'total_today_diff'])

print("\nListo.")
