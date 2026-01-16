
import os
import django
from django.db.models import Sum, Count
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint

def scan_all():
    year = timezone.now().year
    print(f"--- Scanning ALL Points for Spikes > 500 m3 in {year} ---")
    
    # Efficiently group by point to find offenders
    # We want points that have at least one record with total_diff > 500
    
    anomalies = InteractionDetail.objects.filter(
        date_time_medition__year=year,
        total_diff__gt=500
    ).values('catchment_point_id').annotate(
        count=Count('id'),
        total_impact=Sum('total_diff')
    ).order_by('-total_impact')
    
    if not anomalies:
        print("✅ No anomalies found in any other point.")
        return

    print(f"⚠️  Found {len(anomalies)} points with anomalies:")
    for a in anomalies:
        pid = a['catchment_point_id']
        try:
            p = CatchmentPoint.objects.get(id=pid)
            title = p.title
        except:
            title = "Unknown"
            
        print(f"[{pid}] {title}: {a['count']} records, Impact: {a['total_impact']} m3")

if __name__ == '__main__':
    scan_all()
