
import os
import django
from django.utils import timezone
from datetime import timedelta
import pytz

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def debug_2300():
    pid = 87
    chile_tz = pytz.timezone('America/Santiago')
    
    # Target: Dec 29 23:00 Chile time
    # This is Dec 30 02:00 UTC approximately
    
    from datetime import datetime
    start = timezone.make_aware(datetime(2025, 12, 29, 23, 0, 0), chile_tz)
    end = start + timedelta(minutes=59)
    
    print(f"--- Checking Records around {start} (Chile) for Point {pid} ---")

    # Search slightly wider range
    qs = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__range=(start - timedelta(hours=1), end + timedelta(hours=1))
    ).order_by('date_time_medition')
    
    from datetime import datetime
    
    for r in qs:
        print(f"Time: {r.date_time_medition} | Diff: {r.total_diff} | TodayDiff: {r.total_today_diff}")

if __name__ == '__main__':
    debug_2300()
