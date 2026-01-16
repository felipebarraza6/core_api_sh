
import os
import django
from django.utils import timezone
from datetime import timedelta
import pytz

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint
from api.core.serializers.interaction_detail import InteractionDetailModelSerializer

def verify_json_logic():
    pid = 87
    # Target the record that was giving 918/953
    # It was the last record of 2025-12-29
    today = timezone.localtime(timezone.now()).date()
    yesterday = today - timedelta(days=1)
    
    print(f"--- Verifying JSON Logic for Point {pid} on {yesterday} ---")
    
    # Fetch the record
    last_rec = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__date=yesterday
    ).order_by('-date_time_medition').first()
    
    if not last_rec:
        print("No record found.")
        return

    print(f"Testing Record ID: {last_rec.id} Time: {last_rec.date_time_medition}")
    
    # Initialize serializer with context that triggers the batch calculation logic
    # The view passes 'view' in context, but checking the code, 
    # the batch logic runs if 'request_cache' is present or instantiated in to_representation.
    # We simply call to_representation directly or via .data
    
    serializer = InteractionDetailModelSerializer(last_rec, context={})
    data = serializer.data
    
    print(f"Serializer Calculated Total Diff: {data.get('total_diff')}")
    print(f"Serializer Calculated Total Today Diff: {data.get('total_today_diff')}")
    
    expected = 136
    actual = data.get('total_today_diff')
    
    if int(actual) == expected:
        print(f"✅ SUCCESS: Result matches expected ({expected}). Anti-Reset rule is working.")
    else:
        print(f"❌ FAILURE: Result {actual} != Expected {expected}.")

if __name__ == '__main__':
    verify_json_logic()
