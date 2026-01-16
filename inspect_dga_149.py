
import os
import django
import sys

sys.path.append('/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import DgaDataConfigCatchment, InteractionDetail, CatchmentPoint

POINT_ID = 149

def inspect_point():
    try:
        point = CatchmentPoint.objects.get(id=POINT_ID)
        print(f"Point: {point.title} (ID: {point.id})")
        
        config = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
        if config:
            print(f"DGA Config found:")
            print(f"  Code DGA: {config.code_dga}")
            print(f"  RUT Report: {config.rut_report_dga}")
            print(f"  Type: {config.type_dga}")
            print(f"  Standard: {config.standard}")
            print(f"  Password set: {'Yes' if config.password_dga_software else 'No'}")
        else:
            print("No DGA Config found!")

        print("\nRecent InteractionDetails (Last 10):")
        details = InteractionDetail.objects.filter(catchment_point=point).order_by('-created')[:10]
        for d in details:
            print(f"  ID: {d.id}")
            print(f"  Created: {d.created}")
            print(f"  Medition: {d.date_time_medition}")
            print(f"  Send DGA: {d.send_dga}")
            print(f"  Return DGA: {d.return_dga}")
            print(f"  Voucher: {d.n_voucher}")
            print(f"  Is Error: {d.is_error}")
            print("-" * 30)

    except CatchmentPoint.DoesNotExist:
        print(f"Point {POINT_ID} not found.")

if __name__ == "__main__":
    inspect_point()
