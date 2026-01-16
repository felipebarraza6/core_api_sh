
import os
import django
import sys

# Setup Django environment
sys.path.append('/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail
from api.core.admin import InteractionDetailAdmin
from django.contrib.admin.sites import AdminSite

class MockRequest:
    pass

def test_admin_methods():
    print("Testing InteractionDetailAdmin methods...")
    
    # Get a sample object
    obj = InteractionDetail.objects.last()
    if not obj:
        print("No InteractionDetail objects found.")
        return

    print(f"Testing with object ID: {obj.id}")
    
    # Initialize Admin
    admin_instance = InteractionDetailAdmin(InteractionDetail, AdminSite())
    
    methods = [
        'get_catchment_point_display',
        'get_fechas_display',
        'get_pulses_display',
        'get_total_con_escala',
        'get_flow_display',
        'get_consumo_display',
        'get_nivel_display',
        'get_water_table_display',
        'get_send_dga_badge',
        'get_voucher_badge',
        'get_status_badge'
    ]
    
    for method_name in methods:
        try:
            if not hasattr(admin_instance, method_name):
                 print(f"ERROR: Method {method_name} NOT FOUND on admin instance")
                 continue

            method = getattr(admin_instance, method_name)
            result = method(obj)
            print(f"Method {method_name}: OK")
        except Exception as e:
            print(f"ERROR in {method_name}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_admin_methods()
