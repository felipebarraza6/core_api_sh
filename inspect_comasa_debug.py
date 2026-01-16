import os
import django
from django.conf import settings
from datetime import datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, Variable, InteractionDetail, ProfileDataConfigCatchment, SchemesCatchment

def inspect_comasa():
    try:
        # Confirm Comasa P2
        cp = CatchmentPoint.objects.get(id=77)
        print(f"Point: {cp.title} (ID: {cp.id})")
        
        # Check schemes and variables
        print("\n--- Schemes and Variables ---")
        schemes = cp.schemes.all()
        if not schemes:
            print("No schemes found for this point.")
        
        for scheme in schemes:
            print(f"Scheme: {scheme.name} (ID: {scheme.id})")
            vars = scheme.variables.all()
            for v in vars:
                print(f"  Variable ID: {v.id}")
                print(f"    Name (str): {v.str_variable}")
                print(f"    Label: {v.label}")
                print(f"    Type: {v.type_variable}")
                print(f"    Provider: {v.service}")
                print(f"    Addition (Constante): {v.addition}")
                print(f"    Pulses Factor: {v.pulses_factor}")
                print(f"    Convert to Lt: {v.convert_to_lt}")
                
                if v.addition and v.addition != 0:
                    print(f"    !!! Non-zero addition detected: {v.addition} !!!")

        # Check ProfileDataConfig
        print("\n--- Profile Data Config ---")
        try:
            pwc = ProfileDataConfigCatchment.objects.get(point_catchment=cp)
            print(f"  d6 (Caudalimetro inicial): {pwc.d6}")
            print(f"  d1-d5 constants: {pwc.d1}, {pwc.d2}, {pwc.d3}, {pwc.d4}, {pwc.d5}")
        except ProfileDataConfigCatchment.DoesNotExist:
            print("No ProfileDataConfigCatchment found.")

        # Check recent InteractionDetail
        print("\n--- Recent Interactions (Last 3) ---")
        interactions = InteractionDetail.objects.filter(catchment_point=cp).order_by('-date_time_last_logger')[:3]
        for i in interactions:
            print(f"  Time: {i.date_time_last_logger}, Total: {i.total}, Diff: {i.total_diff}")

    except CatchmentPoint.DoesNotExist:
        print("Comasa P2 (ID 77) not found.")

if __name__ == "__main__":
    inspect_comasa()
