import os
import django
import sys
from django.db.models import Sum

# Add the project root to sys.path
sys.path.append('/root/core_api_sh')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail, ProfileDataConfigCatchment

def analyze_duplication_v2():
    print("=== Analyzing Potential Duplication (DB_Total approximation to d6) ===")
    print("This script checks if the last recorded total in the DB is roughly equal to the configured 'd6' offset.")
    print("If they are equal, it often means the Logger is sending the Full Total, but the system is ALSO adding d6.")
    print("This results in doubled values displayed to the user.")
    print("\nRecommended Action: For points listed below, verify if d6 should be 0.")
    print("-" * 110)
    
    points = CatchmentPoint.objects.all()
    affected_count = 0
    
    print(f"{'ID':<5} | {'Title':<40} | {'d6 (Config)':<15} | {'DB Total':<15} | {'Diff %':<10}")
    print("-" * 110)
    
    for p in points:
        # Calculate d6
        d6_val = ProfileDataConfigCatchment.objects.filter(point_catchment=p).aggregate(total=Sum("d6"))["total"] or 0
        try:
            d6_float = float(d6_val)
        except:
            d6_float = 0.0
            
        if d6_float <= 100: # Ignore small offsets
            continue
            
        # Get latest record
        last = InteractionDetail.objects.filter(catchment_point=p).order_by('-date_time_medition').first()
        if not last or not last.total:
            continue
            
        try:
            # Parse total carefully
            clean_val = str(last.total).replace('.', '')
            if ',' in clean_val: clean_val = clean_val.replace(',', '.')
            db_total = float(clean_val)
        except:
            continue
            
        if db_total <= 0:
            continue
            
        # Check if DB Total is close to d6 (within 10% tolerance to be safe)
        diff = abs(db_total - d6_float)
        ratio = diff / d6_float if d6_float > 0 else 0
        
        if ratio < 0.10: # 10% tolerance
            print(f"{p.id:<5} | {str(p.title)[:40]:<40} | {d6_float:<15} | {db_total:<15} | {ratio*100:<10.2f}")
            affected_count += 1
            
    print("-" * 110)
    print(f"Total potential affected points: {affected_count}")
    print("\nTo fix: Go to Admin -> Catchment Point -> Select ID -> Profile Data Config -> Set d6 to 0.")

if __name__ == "__main__":
    analyze_duplication_v2()
