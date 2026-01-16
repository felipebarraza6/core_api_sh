
import os
import django
from django.db.models import Sum
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def check_annual():
    pid = 87
    year = timezone.now().year
    print(f"--- Annual Consumption {year} for San Fernando (ID {pid}) ---")
    
    qs = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__year=year
    )
    
    total = qs.aggregate(s=Sum('total_diff'))['s'] or 0
    print(f"Total Consumed: {total} m3")
    
    # Check for negatives just in case
    neg = qs.filter(total_diff__lt=0).aggregate(s=Sum('total_diff'))['s'] or 0
    if neg < 0:
        print(f"Warning: Includes {neg} m3 of negative adjustments.")

if __name__ == '__main__':
    check_annual()
