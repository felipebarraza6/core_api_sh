
import os
import django
import sys
from datetime import datetime
import pytz

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def check_feb5_end(point_id):
    print(f"Checking Feb 5th End Record for Point {point_id}...")
    
    # Get last record of Feb 5th
    end_feb5 = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__year=2026,
        date_time_medition__month=2,
        date_time_medition__day=5
    ).order_by('-date_time_medition').first()
    
    if end_feb5:
        print(f"Last Record Feb 5th: {end_feb5.date_time_medition}")
        print(f"  Total: {end_feb5.total}")
        print(f"  Pulses: {end_feb5.pulses}")
    else:
        print("No record found for Feb 5th.")
        
    # Get first record Feb 6th
    start_feb6 = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__year=2026,
        date_time_medition__month=2,
        date_time_medition__day=6
    ).order_by('date_time_medition').first()

    if start_feb6:
        print(f"First Record Feb 6th: {start_feb6.date_time_medition}")
        print(f"  Total: {start_feb6.total}")
        print(f"  Pulses: {start_feb6.pulses}")
        
    if end_feb5 and start_feb6:
        # Check raw diff
        diff = int(float(start_feb6.total)) - int(float(end_feb5.total))
        print(f"CALCULATED DIFF: {diff}")

if __name__ == '__main__':
    check_feb5_end(86)
