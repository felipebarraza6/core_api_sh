
import os
import django
from django.db.models import Sum, Max
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def analyze_san_fernando():
    pid = 87
    print(f"--- Analyzing San Fernando (ID {pid}) Consumption ---")
    
    # 1. Check for Massive Spikes (> 500) in general (current year)
    current_year = timezone.now().year
    
    spikes = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__year=current_year,
        total_diff__gt=500
    ).order_by('-total_diff')
    
    if spikes.exists():
        print(f"⚠️  FOUND {spikes.count()} RECORDS > 500 m3 in {current_year}:")
        for s in spikes[:5]:
            print(f"   - {s.date_time_medition}: {s.total_diff} m3")
    else:
        print(f"✅ No massive spikes > 500 m3 found in {current_year}.")

    # 2. Analyze Yesterday (Dec 29) specifically
    today = timezone.localtime(timezone.now()).date()
    yesterday = today - timedelta(days=1)
    
    print(f"\n--- Hourly Profile for Yesterday ({yesterday}) ---")
    
    recs = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__date=yesterday
    ).order_by('date_time_medition')
    
    total_day = 0
    max_hour = 0
    
    print(f"{'Time':<20} | {'Consumption (m3)':<15}")
    print("-" * 40)
    for r in recs:
        diff = r.total_diff or 0
        total_day += diff
        if diff > max_hour: max_hour = diff
        print(f"{r.date_time_medition.strftime('%H:%M') :<20} | {diff:<15}")
        
    print("-" * 40)
    print(f"Total Daily: {total_day}")
    print(f"Max Hourly: {max_hour}")
    
    if max_hour > 100:
        print("⚠️  Warning: Some hourly values are quite high (> 100 m3).")

if __name__ == '__main__':
    analyze_san_fernando()
