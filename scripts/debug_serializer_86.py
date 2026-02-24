
import os
import django
import sys
from datetime import datetime
import pytz

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint
from api.core.serializers.interaction_detail import InteractionDetailModelSerializer

def debug_serializer(point_id):
    print(f"Debugging Serializer for Point {point_id} (Codegua)...")
    
    # Range: Feb 6th
    start_date = '2026-02-06 00:00:00' 
    end_date = '2026-02-06 23:59:59'
    
    records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__range=(start_date, end_date)
    ).order_by('date_time_medition')
    
    print(f"Found {records.count()} records.")
    
    # Mock context
    context = {
        'request_cache': {
             'points_config': {},
             'daily_data': {},
             'prev_record_totals': {}
        }
    }
    
    serializer = InteractionDetailModelSerializer(context=context)
    
    for r in records[:10]: # Check first 10
        print(f"--- Record: {r.date_time_medition} ---")
        print(f"  DB Total: {r.total}")
        print(f"  DB Flow: {r.flow}")
        print(f"  DB Diff: {r.total_diff}")
        
        rep = serializer.to_representation(r)
        
        print(f"  Serializer Total: {rep['total']}")
        print(f"  Serializer Diff: {rep['total_diff']}")
        print(f"  Serializer Flow: {rep['flow']}")
        print(f"  Serializer Flow Type: {rep.get('flow_type')}")

if __name__ == '__main__':
    debug_serializer(86)
