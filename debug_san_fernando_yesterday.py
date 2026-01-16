
import os
import django
from django.utils import timezone
import pytz
from datetime import datetime
from django.db.models import Sum

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail

def debug_san_fernando():
    pid = 87
    print(f"--- Debugging San Fernando (ID {pid}) for Yesterday (Dec 29) ---")
    
    try:
        p = CatchmentPoint.objects.get(id=pid)
        chile_tz = pytz.timezone("America/Santiago")
        
        # Define Yesterday
        # Current server time is Dec 30. So yesterday is Dec 29.
        start = datetime(2025, 12, 29, 0, 0, 0, tzinfo=chile_tz)
        end = datetime(2025, 12, 29, 23, 59, 59, 999999, tzinfo=chile_tz)
        
        records = InteractionDetail.objects.filter(
            catchment_point=p,
            date_time_medition__range=(start, end)
        ).order_by('date_time_medition')
        
        print(f"Found {records.count()} records.")
        print(f"{'Time':<20} | {'Total':<10} | {'Diff':<5} | {'TodayDiff':<10}")
        print("-" * 60)
        
        calculated_sum = 0
        last_today_diff = 0
        
        for r in records:
            ts = r.date_time_medition.astimezone(chile_tz).strftime('%H:%M:%S')
            
            # Calculate running sum manually
            calculated_sum += (r.total_diff or 0)
            last_today_diff = r.total_today_diff
            
            # Print only first few, last few, and anomalies? 
            # Let's print all if count is small (<50), or summary.
            # Assuming hourly (24) + extra -> < 50.
            print(f"{ts:<20} | {r.total:<10} | {r.total_diff:<5} | {r.total_today_diff:<10}")

        print("-" * 60)
        print(f"Calculated Sum of total_diff: {calculated_sum}")
        print(f"Stored total_today_diff (Last Record): {last_today_diff}")
        
    except CatchmentPoint.DoesNotExist:
        print(f"Point {pid} not found")

if __name__ == '__main__':
    debug_san_fernando()
