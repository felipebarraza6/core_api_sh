
import os
import django
from django.utils import timezone
from django.db.models import Sum

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def debug_p77():
    pid = 77
    today = timezone.localtime(timezone.now()).date()
    print(f"--- Debugging Comasa P2 (ID {pid}) for Today ({today}) ---")
    
    # Check for records
    qs = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__date=today
    ).order_by('date_time_medition')
    
    count = qs.count()
    print(f"Total Records Today: {count}")
    
    if count == 0:
        print("No records found for today.")
        return

    # Check Sum
    total_consumed = qs.aggregate(s=Sum('total_diff'))['s']
    print(f"Sum('total_diff'): {total_consumed}")
    
    # Inspect first few records
    for r in qs[:10]:
        print(f"Time: {r.date_time_medition} | Diff: {r.total_diff} | TodayDiff: {r.total_today_diff}")

if __name__ == '__main__':
    debug_p77()
