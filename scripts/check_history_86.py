
import os
import django
import sys
from datetime import datetime

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def check_history(point_id):
    print(f"Checking history for Point {point_id}...")
    
    # Get the last 10 records that have distinct total values or check a range
    # Let's find when the total was NOT 28222
    
    current_stuck_val = 28222
    
    # Find the most recent record where total is NOT close to 28222 (e.g. differs by > 1)
    # Since total is stored as Char or Float, we might need casting. 
    # But usually we can just order by date.
    
    last_records = InteractionDetail.objects.filter(
        catchment_point_id=point_id
    ).order_by('-date_time_medition')[:20]
    
    print("Most recent 20 records:")
    for r in last_records:
        print(f"Date: {r.date_time_medition} | Pulses: {r.pulses} | Total: {r.total}")

    print("-" * 30)
    
    # Try to find the transition point
    # We want records where total != '28222.00' and total != '28222'
    # This might be tricky with string comparison if formatted simply.
    
    # Let's just look for distinct total values in the last 1000 records
    distinct_totals = InteractionDetail.objects.filter(
        catchment_point_id=point_id
    ).values('total').distinct().order_by('total')
    
    print(f"Distinct Total values in DB: {list(distinct_totals)}")
    
    # Let's find the last record with a valid total change
    # We fetch slightly older records
    older_records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__lt='2026-02-01'
    ).order_by('-date_time_medition')[:5]
    
    print("\nRecords from before Feb 1st 2026:")
    for r in older_records:
        print(f"Date: {r.date_time_medition} | Pulses: {r.pulses} | Total: {r.total}")

if __name__ == '__main__':
    check_history(86)
