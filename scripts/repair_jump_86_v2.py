
import os
import django
import sys
from datetime import datetime
import pytz

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def repair_jump_records_v2(point_id):
    print("Repairing Jump Records v2...")
    
    # Target specific hours on Feb 5th using filter components to avoid timezone confusion
    # We want 12:00, 13:00, 14:00 exactly
    
    target_hours = [12, 13, 14]
    
    pulses_factor = 100
    
    for h in target_hours:
        try:
            r = InteractionDetail.objects.get(
                catchment_point_id=point_id,
                date_time_medition__year=2026,
                date_time_medition__month=2,
                date_time_medition__day=5,
                date_time_medition__hour=h
            )
            
            print(f"Processing {r.date_time_medition}")
            print(f"  Old Total: {r.total}, Pulses: {r.pulses}, Diff: {r.total_diff}")
            
            # Recalculate Total
            calculated_total = (float(r.pulses) * pulses_factor) / 1000.0
            new_total_int = int(round(calculated_total))
            new_total_str = str(new_total_int)
            
            if r.total != new_total_str:
                print(f"  Fixing Total: {r.total} -> {new_total_str}")
                r.total = new_total_str
                r.save()
            
            # Recalculate Diff (vs previous hour)
            # Find previous
            prev = InteractionDetail.objects.filter(
                catchment_point_id=point_id,
                date_time_medition__lt=r.date_time_medition
            ).order_by('-date_time_medition').first()
            
            if prev and prev.total:
                # Ensure prev total is int for calculation
                try:
                    prev_total = int(float(prev.total))
                    curr_total = int(float(r.total))
                    diff = curr_total - prev_total
                    if diff < 0: diff = 0 # protection
                    
                    if r.total_diff != diff:
                        print(f"  Fixing Diff: {r.total_diff} -> {diff}")
                        r.total_diff = diff
                        r.save()
                        
                        # Fix Flow for this record too
                        # If diff is HUGE, flow will be huge. 
                        # But valid flow for that specific hour.
                        # Diff occurs over 3600 seconds
                        flow = (diff / 3600.0) * 1000.0
                        r.flow = round(flow, 2)
                        print(f"  Fixing Flow: -> {r.flow}")
                        r.save()
                        
                except ValueError:
                    pass
                    
        except InteractionDetail.DoesNotExist:
            print(f"Record for hour {h} not found")

if __name__ == '__main__':
    repair_jump_records_v2(86)
