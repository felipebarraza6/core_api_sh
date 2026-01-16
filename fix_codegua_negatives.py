
import os
import django
from django.db.models import Sum

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def fix_negatives():
    pid = 86
    print(f"--- Cleaning Negative Spikes for Codegua (ID {pid}) ---")
    
    qs = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        total_diff__lt=0
    )
    
    count = qs.count()
    if count == 0:
        print("No negative records found.")
        return

    print(f"Found {count} negative records.")
    
    # Calculate impact
    neg_sum = qs.aggregate(s=Sum('total_diff'))['s'] or 0
    print(f"These records contribute {neg_sum} m3 to the annual total.")
    
    # Update
    updated = qs.update(total_diff=0)
    print(f"✅ Updated {updated} records to total_diff = 0.")

if __name__ == '__main__':
    fix_negatives()
