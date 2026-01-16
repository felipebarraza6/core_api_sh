
import os
import django
import sys

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint

def check_vouchers():
    print("Checking Vouchers Data...")
    
    # 1. Total records with voucher
    total_vouchers = InteractionDetail.objects.filter(n_voucher__isnull=False).count()
    print(f"Total records with n_voucher != None: {total_vouchers}")
    
    total_non_empty = InteractionDetail.objects.filter(n_voucher__isnull=False).exclude(n_voucher='').count()
    print(f"Total records with n_voucher != None AND != '': {total_non_empty}")

    if total_non_empty == 0:
        print("CRITICAL: No valid vouchers found in DB!")
        return

    # 2. Check distinct logic
    try:
        latest = InteractionDetail.objects.filter(
            n_voucher__isnull=False
        ).exclude(n_voucher='').order_by('catchment_point_id', '-date_time_medition').distinct('catchment_point_id')
        
        print(f"Distinct vouchers found for {latest.count()} points.")
        
        for item in latest[:5]:
            print(f"Point: {item.catchment_point_id} | Voucher: {item.n_voucher} | Date: {item.date_time_medition}")
            
    except Exception as e:
        print(f"Error checking distinct query: {e}")

if __name__ == '__main__':
    check_vouchers()
