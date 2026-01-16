
import os
import django
import sys

sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint

def verify_point_63():
    target_id = 63
    print(f"🚀 Verifying Logic for Point {target_id}...")

    # 1. Mock having Point 63 in the list
    unique_point_ids_voucher = [target_id]
    
    # 2. Run the OPTIMIZED VOUCHER LOGIC
    latest_vouchers_map = {}
    try:
        latest_vouchers_qs = InteractionDetail.objects.filter(
            catchment_point_id__in=unique_point_ids_voucher,
            n_voucher__isnull=False
        ).exclude(n_voucher='').order_by('catchment_point_id', '-date_time_medition').distinct('catchment_point_id')
        
        latest_vouchers_map = {v.catchment_point_id: v for v in latest_vouchers_qs}
        print(f"💰 Map size: {len(latest_vouchers_map)}")
        
        if target_id in latest_vouchers_map:
            v = latest_vouchers_map[target_id]
            print(f"✅ FOUND in Map: {v.n_voucher}")
        else:
            print(f"❌ NOT FOUND in Map")
            
    except Exception as e:
        print(f"❌ Error optimizando vouchers: {e}")

if __name__ == '__main__':
    verify_point_63()
