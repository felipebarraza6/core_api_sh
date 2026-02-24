
import os
import django
import sys
from datetime import datetime

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail, Variable, ProfileDataConfigCatchment, SchemesCatchment

def inspect_point(point_id):
    try:
        point = CatchmentPoint.objects.get(id=point_id)
        print(f"Inspecting Point ID: {point.id}")
        print(f"Title: {point.title}")
        print(f"Project: {point.project}")
        print(f"Owner: {point.owner_user}")
        print(f"Provider Flags: Novus={point.is_novus}, Twin={point.is_tdata}, Nettra={point.is_thethings}")

        # Check Profile Data Config
        try:
            profile_config = ProfileDataConfigCatchment.objects.get(point_catchment=point)
            print("\nProfile Data Config:")
            print(f"  Addition (Reset): {profile_config.addition}")
            print(f"  D6 (Caudalimetro inicial): {profile_config.d6}")
            print(f"  Date Start Telemetry: {profile_config.date_start_telemetry}")
        except ProfileDataConfigCatchment.DoesNotExist:
            print("\nNo ProfileDataConfigCatchment found.")

        # Check Variables
        print("\nVariables:")
        schemes = point.schemes.all()
        for scheme in schemes:
            print(f"  Scheme: {scheme.name} (ID: {scheme.id})")
            variables = Variable.objects.filter(scheme_catchment=scheme)
            for var in variables:
                print(f"    Variable Type: {var.type_variable} (ID: {var.id})")
                print(f"      Label: {var.label}")
                print(f"      Pulses Factor: {var.pulses_factor}")
                print(f"      Service: {var.service}")

        # Check Recent Interactions
        print("\nRecent InteractionDetails (Last 5):")
        interactions = InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition')[:5]
        for interaction in interactions:
            print(f"  Date: {interaction.date_time_medition}")
            print(f"    Last Logger: {interaction.date_time_last_logger}")
            print(f"    Pulses: {interaction.pulses}")
            print(f"    Total: {interaction.total}")
            print(f"    Total Diff: {interaction.total_diff}")
            print(f"    Flow: {interaction.flow}")
    
    except CatchmentPoint.DoesNotExist:
        print(f"Point with ID {point_id} does not exist.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    inspect_point(86)
