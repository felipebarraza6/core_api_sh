
import os
import django
from django.db.models import Sum, Count
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def fix_global():
    year = timezone.now().year
    limit = 500
    print(f"--- GLOBAL CLEANUP: Removing Spikes > {limit} m3 in {year} ---")
    
    qs = InteractionDetail.objects.filter(
        date_time_medition__year=year,
        total_diff__gt=limit
    )
    
    count = qs.count()
    if count == 0:
        print("✅ No anomalies found to clean.")
        return

    print(f"⚠️  Found {count} records/spikes across the platform.")
    
    # Calculate total impact before deletion
    total_impact = qs.aggregate(s=Sum('total_diff'))['s'] or 0
    print(f"📉 Total Volume to be removed: {total_impact:,.0f} m3")
    
    # Update to 0
    updated = qs.update(total_diff=0)
    print(f"✅ Successfully updated {updated} records to total_diff = 0.")
    print("✨ System data integrity restored.")

if __name__ == '__main__':
    fix_global()
