import os
import django
import sys

sys.path.append('/root/core_api_sh')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.models import CatchmentPoint

def search_cp():
    print("Searching for CatchmentPoints...")
    
    terms = ['Talca', 'Coihueco', 'Coichueco', 'Udetalca']
    for term in terms:
        qs = CatchmentPoint.objects.filter(title__icontains=term)
        for cp in qs:
            print(f"Found ({term}): ID={cp.id}, Title={cp.title}, Active={cp.data_config_profiles.get('is_telemetry', False)}, Freq={cp.frecuency}")
            print(f"   Config: {cp.profile_data_config}")

if __name__ == "__main__":
    search_cp()
