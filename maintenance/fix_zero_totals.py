
import os
import django
import sys
from decimal import Decimal

sys.path.append('/app')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint, ProfileDataConfigCatchment
from api.cronjobs.telemetry.controllers.total import total_m3

def fix_zero_totals(dry_run=True):
    print(f"Starting Fix Zero Totals Script (Dry Run: {dry_run})...")
    
    # Filter suspects: pulses > 0 AND (total='0' OR total='0.0' OR total='0.00')
    # Using istartswith might be safer if there are variations like '0.000'
    suspects = InteractionDetail.objects.filter(pulses__gt=0).exclude(total__isnull=True)
    
    count_fixed = 0
    count_skipped = 0
    
    for record in suspects.iterator():
        try:
            current_total_float = float(record.total)
            if current_total_float != 0:
                continue
                
            # Double check pulses
            if record.pulses <= 0:
                continue
                
            # Get Factor
            # We need to look up the variable config efficiently. 
            # Ideally we'd pre-fetch schemes but for safety/simplicity we'll do it per point or cache it.
            # But the 'pulses_factor' is on the Variable model. We don't have a direct link from InteractionDetail to Variable easily without knowing the scheme.
            # However, usually points have 1 TOTALIZED variable.
            
            point = record.catchment_point
            
            # Find the TOTALIZED variable for this point
            factor = 1000 # Default
            found_var = False
            
            for scheme in point.schemes.all():
                for var in scheme.variables.all():
                    if var.type_variable == 'TOTALIZADO':
                        if var.pulses_factor:
                            factor = var.pulses_factor
                        found_var = True
                        break
                if found_var: 
                    break
            
            # Calculate correct total (RAW)
            # Assumption: The 'offset' (addition) was 0 when this was recorded as 0. 
            # Or simpler: The value SHOULD represent the reading at that time.
            # If we just re-calculate (pulses * factor / 1000), we get the raw m3.
            # If the original intention was raw m3 + 0 offset, this is correct.
            
            calculated_total = (float(record.pulses) * float(factor)) / 1000.0
            
            if calculated_total == 0:
                 # If calculation is still 0 (e.g. pulses=0), skip
                 continue
                 
            # Round to 2 decimals
            new_total = round(calculated_total, 2)
            
            print(f"[FIX] ID: {record.id} | Date: {record.date_time_medition} | Point: {point.id} | Pulses: {record.pulses} | Factor: {factor} | Old Total: {record.total} -> New Total: {new_total}")
            
            if not dry_run:
                record.total = str(new_total)
                # Also fix total_diff and total_today_diff if needed? 
                # For now let's just fix the TOTAL which is the source of truth for graphs.
                # Actually, diffs might be wrong too (0), but fixing TOTAL is the priority. 
                # Updating diffs safely would require traversing the whole timeline which is risky and slow.
                record.save(update_fields=['total'])
                
            count_fixed += 1
            
        except Exception as e:
            print(f"[ERROR] ID {record.id}: {e}")
            count_skipped += 1

    print(f"\nProcessing complete.")
    print(f"Records fixed (or would be): {count_fixed}")
    print(f"Records skipped/error: {count_skipped}")

if __name__ == "__main__":
    # Check for execution flag
    DRY_RUN = True
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        DRY_RUN = False
        
    fix_zero_totals(dry_run=DRY_RUN)
