
import os
import django
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def recalc_daily():
    pid = 87
    today = timezone.localtime(timezone.now()).date()
    yesterday = today - timedelta(days=1)
    
    print(f"--- Recalculating Daily Accumulators for San Fernando (ID {pid}) on {yesterday} ---")
    
    recs = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__date=yesterday
    ).order_by('date_time_medition')
    
    accum = 0
    updated_count = 0
    
    for r in recs:
        # Assuming total_diff is now correct/cleaned
        diff = r.total_diff or 0
        accum += diff
        
        # Only update if different to save DB writes
        if r.total_today_diff != accum:
            r.total_today_diff = accum
            r.save(update_fields=['total_today_diff'])
            updated_count += 1
            
    print(f"✅ Recalculated {recs.count()} records.")
    print(f"Updated {updated_count} records.")
    print(f"Final Accumulator (Total Daily Consumption): {accum}")

if __name__ == '__main__':
    recalc_daily()
