
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def debug_paradox():
    pid = 77
    print(f"--- Debugging Paradox for Point {pid} ---")
    
    qs = InteractionDetail.objects.filter(catchment_point_id=pid)
    
    # 1. Count
    print(f"Total Count: {qs.count()}")
    
    # 2. Latest by date_time_medition
    latest_dt = qs.order_by('-date_time_medition').first()
    print(f"Latest by dt: {latest_dt.date_time_medition} (ID: {latest_dt.id})")
    
    # 3. Latest by ID
    latest_id = qs.order_by('-id').first()
    print(f"Latest by ID: {latest_id.date_time_medition} (ID: {latest_id.id})")
    
    # 4. Check if today's records exist in QS
    from django.utils import timezone
    today = timezone.localtime(timezone.now()).date()
    today_qs = qs.filter(date_time_medition__date=today)
    print(f"Today Records Count: {today_qs.count()}")
    if today_qs.exists():
         latest_today = today_qs.order_by('-date_time_medition').first()
         print(f"Latest Today Record: {latest_today.date_time_medition} (ID: {latest_today.id})")

if __name__ == '__main__':
    debug_paradox()
