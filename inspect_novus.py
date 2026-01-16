import os
import django
import sys
from datetime import date, timedelta
from django.utils import timezone

# Add the project root to sys.path
sys.path.append('/root/core_api_sh')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail

def inspect_novus():
    print("=== Inspecting Novus Points (is_novus=True) ===")
    
    # Find Novus points
    novus_points = CatchmentPoint.objects.filter(is_novus=True)
    print(f"Found {novus_points.count()} Novus points.")
    
    today = timezone.localtime(timezone.now()).date()
    yesterday = today - timedelta(days=1)
    
    print(f"\nChecking records for Today ({today}) and Yesterday ({yesterday})...")
    print(f"{'ID':<5} | {'Title':<30} | {'Date':<12} | {'Records':<8} | {'Null Logger':<12} | {'Example Last Logger'}")
    print("-" * 110)
    
    for p in novus_points:
        for d in [yesterday, today]:
            qs = InteractionDetail.objects.filter(
                catchment_point=p,
                date_time_medition__date=d
            )
            count = qs.count()
            if count == 0:
                print(f"{p.id:<5} | {str(p.title)[:30]:<30} | {str(d):<12} | {count:<8} | {'-':<12} | {'-'}")
                continue
                
            null_logger_count = qs.filter(date_time_last_logger__isnull=True).count()
            
            # Get one example
            last_rec = qs.order_by('-date_time_medition').first()
            last_logger_val = str(last_rec.date_time_last_logger) if last_rec else "None"
            
            print(f"{p.id:<5} | {str(p.title)[:30]:<30} | {str(d):<12} | {count:<8} | {null_logger_count:<12} | {last_logger_val}")

if __name__ == "__main__":
    inspect_novus()
