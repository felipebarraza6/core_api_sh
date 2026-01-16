
import os
import django
from django.db.models import Sum

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def fix_san_fernando():
    pid = 87
    limit = 500
    print(f"--- Cleaning Spikes for San Fernando (ID {pid}) > {limit} m3 ---")
    
    qs = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        total_diff__gt=limit
    )
    
    count = qs.count()
    if count == 0:
        print("No spikes found!")
        return

    print(f"Found {count} records with excessive consumption.")
    
    # Calculate impact
    spike_sum = qs.aggregate(s=Sum('total_diff'))['s'] or 0
    print(f"These records contribute {spike_sum} m3 to the annual total.")
    
    # Update
    updated = qs.update(total_diff=0)
    print(f"✅ Updated {updated} records to total_diff = 0.")

if __name__ == '__main__':
    fix_san_fernando()
