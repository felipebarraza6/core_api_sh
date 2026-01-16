
import os
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def recalc_comasa():
    pid = 77
    today = timezone.localtime(timezone.now()).date()
    
    print(f"--- Recalculating Daily Accumulators for Comasa P2 (ID {pid}) on {today} ---")
    
    recs = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__date=today
    ).order_by('date_time_medition')
    
    accum = 0
    updated_count = 0
    
    for r in recs:
        diff = r.total_diff or 0
        accum += diff
        
        # Only update if different
        if r.total_today_diff != accum:
            r.total_today_diff = accum
            r.save(update_fields=['total_today_diff'])
            updated_count += 1
            
    print(f"✅ Recalculated {recs.count()} records.")
    print(f"Updated {updated_count} records.")
    print(f"Final Accumulator: {accum}")

if __name__ == '__main__':
    recalc_comasa()
