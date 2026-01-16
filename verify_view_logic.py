
import os
import django
import sys
import logging

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint
from django.utils import timezone

def verify_logic():
    print("🚀 Verifying View Logic...")

    # 1. Mock Recent Interactions (Get latest 10)
    recent_interactions = list(InteractionDetail.objects.all().order_by('-date_time_medition')[:10])
    point_ids_voucher = [i.catchment_point_id for i in recent_interactions]
    unique_point_ids_voucher = list(set(point_ids_voucher))
    
    print(f"Points to check: {unique_point_ids_voucher}")

    # 2. Run the OPTIMIZED VOUCHER LOGIC EXACTLY AS IN VIEW
    latest_vouchers_map = {}
    if unique_point_ids_voucher:
        try:
            latest_vouchers_qs = InteractionDetail.objects.filter(
                catchment_point_id__in=unique_point_ids_voucher,
                n_voucher__isnull=False
            ).exclude(n_voucher='').order_by('catchment_point_id', '-date_time_medition').distinct('catchment_point_id')
            
            latest_vouchers_map = {v.catchment_point_id: v for v in latest_vouchers_qs}
            print(f"💰 Map size: {len(latest_vouchers_map)}")
        except Exception as e:
            print(f"❌ Error optimizando vouchers: {e}")

    # 3. Simulate the LOOP
    print("\n--- Simulating Loop ---")
    for interaction in recent_interactions:
        point = interaction.catchment_point
        # point.id is int?
        print(f"Checking Point: {point.id} (Type: {type(point.id)})")
        
        if point.id in latest_vouchers_map:
            voucher_obj = latest_vouchers_map[point.id]
            print(f"✅ FOUND: {voucher_obj.n_voucher}")
        else:
            print(f"❌ MISSING")

if __name__ == '__main__':
    verify_logic()
