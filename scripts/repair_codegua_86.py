
import os
import django
import sys
from datetime import datetime

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, Variable

def repair_codegua(point_id):
    print(f"Repairing Point {point_id} (Codegua)...")
    
    # Range to fix: From the jump onwards
    start_date = '2026-02-05 11:00:00' 
    # We start a bit before to ensure we catch the transition
    
    records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=start_date
    ).order_by('date_time_medition')
    
    # Get the correct factor
    # We know from inspection it is 100 for Total logic
    # But let's verify from the variable
    # But for this script I can hardcode it if I am sure, or fetch it.
    
    # Based on user confirmation and previous inspection:
    pulses_factor = 100 
    
    print(f"Using Pulses Factor: {pulses_factor}")
    print(f"Found {records.count()} records to check/fix.")
    
    updated_count = 0
    
    for r in records:
        if r.pulses is None:
            continue
            
        # Calculate expected total
        # Formula: (pulses * factor) / 1000
        # Assuming offset is 0 as seen in inspection
        
        calculated_total = (float(r.pulses) * pulses_factor) / 1000.0
        
        # Round to integer for Total field?
        # Model definition: total = models.CharField(...)
        # Usually stored as string of float or int.
        # In DB values shown as '28222.00', which is float string.
        # But 'total_m3' controller returns int usually?
        # Let's match the requested format. '28222.00' suggests it stores decimals.
        
        # Let's store as .2f to be safe formatted string
        new_total_str = f"{calculated_total:.2f}"
        
        if r.total != new_total_str:
            print(f"Fixing {r.date_time_medition}: Pulses {r.pulses} | Old Total {r.total} -> New Total {new_total_str}")
            r.total = new_total_str
            
            # We should also update total_today_diff and total_diff ideally
            # But fixing 'total' is the main blocker. The cronjob calculates diffs based on total.
            # If we fix total, the next run might still be confused if we don't fix diffs?
            # Actually, if we fix historical totals, the cronjob won't run on them.
            # But the NEXT cronjob run will see a valid 'last_total' match.
            
            # Let's just fix TOTAL for now.
            r.save()
            updated_count += 1
            
    print(f"Process complete. Updated {updated_count} records.")

if __name__ == '__main__':
    repair_codegua(86)
