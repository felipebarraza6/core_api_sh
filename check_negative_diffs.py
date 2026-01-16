
import os
import django
from django.db.models import Sum

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def check_negatives():
    pid = 86
    print(f"--- Checking Negative Diffs for Codegua (ID {pid}) ---")
    
    qs = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        total_diff__lt=0
    )
    
    count = qs.count()
    neg_sum = qs.aggregate(s=Sum('total_diff'))['s'] or 0
    
    print(f"Found {count} records with negative diff.")
    print(f"Sum of negative diffs: {neg_sum}")
    
    if count > 0:
        print("Sample negatives:")
        for r in qs[:5]:
            print(f"  {r.date_time_medition}: {r.total_diff}")

if __name__ == '__main__':
    check_negatives()
