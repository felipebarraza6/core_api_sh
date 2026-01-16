
import os
import django
import sys
import logging

sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail

def check():
    title = 'Planta complejo P1'
    print(f"Checking Point Title: {title}")
    
    try:
        p = CatchmentPoint.objects.filter(title__icontains=title).first()
        if not p:
            print("❌ Point NOT FOUND")
            # List some points
            print(f"First 5 points: {[p.title for p in CatchmentPoint.objects.all()[:5]]}")
            return

        print(f"✅ Point Found: ID={p.id} | Title={p.title}")
        
        # Check vouchers
        vouchers_count = InteractionDetail.objects.filter(catchment_point=p, n_voucher__isnull=False).exclude(n_voucher='').count()
        print(f"💰 Valid Vouchers Count: {vouchers_count}")
        
        if vouchers_count > 0:
            last = InteractionDetail.objects.filter(catchment_point=p, n_voucher__isnull=False).exclude(n_voucher='').order_by('-date_time_medition').first()
            print(f"📝 Latest Voucher: {last.n_voucher}")
            print(f"📅 Date: {last.date_time_medition}")
        else:
            print("❌ NO VOUCHERS for this point.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    check()
