
import os
import django
import sys

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def check_feb5_jump(point_id):
    records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__range=('2026-02-05 10:00:00', '2026-02-05 16:00:00')
    ).order_by('date_time_medition')
    
    print("Checking Feb 5th Jump Records:")
    for r in records:
        print(f"Date: {r.date_time_medition} | Pulses: {r.pulses} | Total: {r.total} | Diff: {r.total_diff}")

if __name__ == '__main__':
    check_feb5_jump(86)
