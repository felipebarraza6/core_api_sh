import os
import django
import sys
from django.db.models import F
from datetime import timedelta
from django.utils import timezone

# Add the project root to sys.path
sys.path.append('/root/core_api_sh')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail

def fix_novus_dates():
    print("=== Fixing Novus Missing Dates (Today & Yesterday) ===")
    
    # 1. Get Novus Points
    novus_ids = list(CatchmentPoint.objects.filter(is_novus=True).values_list('id', flat=True))
    if not novus_ids:
        print("No Novus points found.")
        return
        
    print(f"Targeting {len(novus_ids)} Novus points: {novus_ids}")
    
    # 2. Define Date Range
    today = timezone.localtime(timezone.now()).date()
    yesterday = today - timedelta(days=1)
    
    # 3. Update
    qs = InteractionDetail.objects.filter(
        catchment_point_id__in=novus_ids,
        date_time_medition__date__gte=yesterday,
        date_time_last_logger__isnull=True
    )
    
    count = qs.count()
    print(f"Found {count} records with NULL logger date.")
    
    if count > 0:
        print("Applying fix (setting last_logger = medition)...")
        updated = qs.update(date_time_last_logger=F('date_time_medition'))
        print(f"✅ Updated {updated} records.")
    else:
        print("✅ No records needed fixing.")

if __name__ == "__main__":
    fix_novus_dates()
