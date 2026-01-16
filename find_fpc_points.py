
import os
import django
import sys

sys.path.append('/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import DgaDataConfigCatchment, CatchmentPoint

def check_other_points():
    print("Searching for FPC Tissue points...")
    points = CatchmentPoint.objects.filter(title__icontains="Tissue") | CatchmentPoint.objects.filter(title__icontains="FPC")
    
    for p in points:
        print(f"Found Point: {p.id} - {p.title}")
        config = DgaDataConfigCatchment.objects.filter(point_catchment=p).first()
        if config:
            print(f"  Code: {config.code_dga}")
            print(f"  RUT: {config.rut_report_dga}")
        else:
            print("  No DGA Config")

if __name__ == "__main__":
    check_other_points()
