import os
import django
from django.db.models import Q

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import Variable, ProfileDataConfigCatchment

def analyze_constants():
    print(f"{'CLIENTE':<30} | {'PUNTO':<40} | {'VARIABLE':<20} | {'ADICIÓN':<15}")
    print("-" * 115)
    
    vars_with_addition = Variable.objects.filter(addition__isnull=False).exclude(addition=0)
    count = 0
    
    for v in vars_with_addition:
        count += 1
        scheme = v.scheme_catchment
        # Get points associated with this scheme
        points = scheme.points_catchment.all()
        
        if not points:
             print(f"{'SIN PUNTO':<30} | {'Unknown':<40} | {v.str_variable:<20} | {v.addition:<15}")
             continue

        for p in points:
            client_name = "N/A"
            try:
                if p.project and p.project.client:
                    client_name = p.project.client.name
            except Exception:
                pass
            
            # Format number with separators
            add_fmt = f"{v.addition:,}"
            
            print(f"{client_name[:30]:<30} | {p.title[:40]:<40} | {v.str_variable[:20]:<20} | {add_fmt:<15}")


if __name__ == "__main__":
    analyze_constants()
