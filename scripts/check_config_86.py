
import os
import django
import sys

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, Variable

def check_config(point_id):
    print(f"Checking Config for Point {point_id}...")
    
    point = CatchmentPoint.objects.get(id=point_id)
    
    # Check DGA Standard
    dga = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
    if dga:
        print(f"DGA Standard: {dga.standard}")
    else:
        print("No DGA Config found.")
        
    # Check has_avg_flow query
    # Logic from serializer:
    # Variable.objects.filter(type_variable="CAUDAL_PROMEDIO", scheme_catchment__points_catchment=catchment_point).exists()
    
    has_avg = Variable.objects.filter(
        type_variable="CAUDAL_PROMEDIO", 
        scheme_catchment__points_catchment=point
    ).exists()
    
    print(f"has_avg_flow (Serializer Logic): {has_avg}")
    
    # Check what variables exist
    vars = Variable.objects.filter(scheme_catchment__points_catchment=point)
    for v in vars:
        print(f"Variable: {v.type_variable} (Scheme: {v.scheme_catchment.name})")

if __name__ == '__main__':
    check_config(86)
