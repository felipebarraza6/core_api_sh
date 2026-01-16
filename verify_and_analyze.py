
import os
import django
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail
from api.core.serializers.catchment_points import CatchmentPointIkoluSerializer

def run_analysis():
    print("=== 1. Verifying San Fernando (ID 87) Daily Consumption ===")
    try:
        p87 = CatchmentPoint.objects.get(id=87)
        # Simulate Batch Data to ensure it doesn't override logic
        today = timezone.localtime(timezone.now()).date()
        yesterday = today - timedelta(days=1)
        
        # Make sure we import what we need (the serializer handles it)
        serializer = CatchmentPointIkoluSerializer(p87, context={}) 
        data = serializer.data
        
        val_yesterday = data['modules']['total_consumed_yesterday']
        print(f"San Fernando (87) Yesterday Consumption (Serializer): {val_yesterday}")
        
        # Manual Check
        manual_sum = InteractionDetail.objects.filter(
            catchment_point_id=87,
            date_time_medition__date=yesterday
        ).aggregate(s=Sum('total_diff'))['s']
        print(f"San Fernando (87) Yesterday Manual Sum: {manual_sum}")
        
        if val_yesterday == manual_sum:
            print("✅ Serializer matches Manual Sum.")
        else:
            print("❌ Mismatch!")
            
    except Exception as e:
        print(f"Error checking San Fernando: {e}")

    print("\n=== 2. Analyzing Codegua (ID 86) Annual Consumption Anomalies ===")
    try:
        p86 = CatchmentPoint.objects.get(id=86)
        current_year = timezone.now().year
        
        qs = InteractionDetail.objects.filter(
            catchment_point=p86,
            date_time_medition__year=current_year
        ).order_by('total_diff')
        
        total_recs = qs.count()
        total_sum = qs.aggregate(s=Sum('total_diff'))['s'] or 0
        
        print(f"Total Records: {total_recs}")
        print(f"Total Sum (Annual): {total_sum}")
        
        # Check for active spikes (e.g., > 500 m3 in an hour?)
        threshold = 500
        spikes = qs.filter(total_diff__gt=threshold).order_by('-total_diff')
        
        if spikes.exists():
            print(f"⚠️ FOUND {spikes.count()} RECORDS with diff > {threshold} m3:")
            for s in spikes[:10]:
                print(f"   - {s.date_time_medition}: {s.total_diff} m3 (Total: {s.total})")
        else:
            print(f"✅ No massive spikes > {threshold} m3 found.")

        # Check for negative diffs? (Should be 0, generally filtered out in logic or stored as 0)
        # Assuming total_diff is typically >= 0.
        
    except Exception as e:
        print(f"Error checking Codegua: {e}")

if __name__ == '__main__':
    run_analysis()
