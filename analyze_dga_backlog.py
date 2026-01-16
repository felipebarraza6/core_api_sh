
import os
import django
import sys
from django.db.models import Count

sys.path.append('/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def analyze_backlog():
    print("Analyzing DGA Backlog...")
    pending = InteractionDetail.objects.filter(send_dga=True).values('catchment_point__id', 'catchment_point__title', 'catchment_point__project__client__name').annotate(count=Count('id')).order_by('-count')
    
    print(f"{'Point ID':<10} | {'Point Title':<15} | {'Client':<20} | {'Count':<10}")
    print("-" * 65)
    
    total = 0
    for p in pending:
        pid = p['catchment_point__id']
        title = p['catchment_point__title'] or "N/A"
        client = p['catchment_point__project__client__name'] or "N/A"
        count = p['count']
        total += count
        print(f"{pid:<10} | {title:<15} | {client:<20} | {count:<10}")
    
    print("-" * 65)
    print(f"Total Pending: {total}")

if __name__ == "__main__":
    analyze_backlog()
