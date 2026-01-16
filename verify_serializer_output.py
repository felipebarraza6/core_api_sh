
import os
import django
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail
from api.core.serializers.catchment_points import CatchmentPointIkoluSerializer

def verify_serializer_output():
    pid = 77 # Comasa P2
    print(f"--- Verifying Serializer Output for Point {pid} ---")
    try:
        p = CatchmentPoint.objects.get(id=pid)
        
        # Simulate Batch Data logic from UserProfile (roughly)
        today = timezone.localtime(timezone.now()).date()
        yesterday = today - timedelta(days=1)
        
        recs = InteractionDetail.objects.filter(
            catchment_point=p,
            date_time_medition__date=yesterday
        ).order_by('date_time_medition')
        
        today_recs = InteractionDetail.objects.filter(
            catchment_point=p,
            date_time_medition__date=today
        ).order_by('date_time_medition')
        
        real_latest = today_recs.last()
        if not real_latest: real_latest = recs.last() # Fallback to yesterday

        batch_data = {
            'yesterday_records': {
                p.id: list(recs)
            },
            'today_records': {
                p.id: list(today_recs)
            },
            'latest_records': {
                p.id: real_latest
            }
        }
        
        context = {
            'batch_data': batch_data
        }

        serializer = CatchmentPointIkoluSerializer(p, context=context)
        data = serializer.data
        
        modules = data.get('modules', {})
        total_yesterday = modules.get('total_consumed_yesterday', 'NOT FOUND')
        total_today = modules.get('total_consumed_today', 'NOT FOUND')
        total_year = modules.get('total_consumed_year', 'NOT FOUND')
        
        print(f"Point: {p.title}")
        import json
        # Use a custom encoder for datetime objects if needed, or str()
        print("Full Serializer Output (Keys):")
        print(list(serializer.data.keys()))
        modules = serializer.data['modules']
        print(f"Total Consumed Today: {modules['total_consumed_today']}")
        print(f"Last Data Yesterday: {modules.get('last_data_yesterday')}")
        # Check inside 'm1' (Latest Record)
        m1 = modules.get('m1')
        if m1:
            print(f"M1 (Latest) Total Diff: {m1.get('total_diff')}")
            print(f"M1 (Latest) Today Diff: {m1.get('total_today_diff')}")
        
        # Check 'today' logic
        today_list = modules.get('today', [])
        if today_list:
            print(f"Today List Length: {len(today_list)}")
            print(f"First Item in Today List (Newest): {today_list[0]}")
            print(f"Last Item in Today List (Oldest): {today_list[-1]}")

        print(f"Total Yesterday (Serializer): {total_yesterday}")
        print(f"Total Today (Serializer): {total_today}")
        print(f"Total Year (Serializer): {total_year}")

    except CatchmentPoint.DoesNotExist:
        print(f"Point {pid} not found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    verify_serializer_output()
