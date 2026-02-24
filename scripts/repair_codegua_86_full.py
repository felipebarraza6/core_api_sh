
import os
import django
import sys
from datetime import datetime
import pytz

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint
from api.cronjobs.telemetry.controllers.flow import average_flow

def repair_codegua_full(point_id):
    print(f"Repairing Point {point_id} (Codegua) - FULL Update...")
    
    # Range to fix: From Feb 5th 12:00 onwards
    start_date = '2026-02-05 11:00:00' 
    
    chile = pytz.timezone("America/Santiago")
    
    # Fetch point as dict for average_flow (expects dict with id)
    # Actually average_flow expects point_catchment dict with ID
    # Let's create a minimal dict
    point_dict = {"id": point_id}
    
    records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=start_date
    ).order_by('date_time_medition')
    
    pulses_factor = 100 
    
    print(f"Found {records.count()} records to check/fix.")
    
    updated_count = 0
    
    # We need to iterate carefully to have context of previous record for diffs
    # Since we are fixing sequentially, we can fetch the previous one from DB or keep in memory.
    
    for i, r in enumerate(records):
        if r.pulses is None:
            continue
            
        print(f"Processing {r.date_time_medition}...")
        
        # 1. Update Total (System expects INT string, not decimals)
        calculated_total = (float(r.pulses) * pulses_factor) / 1000.0
        new_total_int = int(round(calculated_total))
        new_total_str = str(new_total_int)
        
        if r.total != new_total_str:
             print(f"  Fixing Total: {r.total} -> {new_total_str}")
             r.total = new_total_str
        
        # 2. Update Total Diff (Consumption)
        # Find previous record (strictly before this one)
        prev = InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__lt=r.date_time_medition
        ).exclude(total__isnull=True).order_by('-date_time_medition').first()
        
        if prev:
            diff = float(r.total) - float(prev.total)
            if diff < 0: diff = 0 # Safety
            rounded_diff = int(round(diff))
            
            if r.total_diff != rounded_diff:
                print(f"  Fixing Diff: {r.total_diff} -> {rounded_diff}")
                r.total_diff = rounded_diff
        else:
            print("  No previous record found for diff.")
            
        # 3. Update Flow (Average Flow)
        # average_flow(point_catchment, total, date_lg, exclude_id=None, current_logger_dt=None)
        # Note: average_flow expects 'total' as int or float.
        # It calculates diff internally against previous record.
        
        # r.date_time_medition is localized? Django models usually return localized if USE_TZ=True
        # average_flow handles it.
        
        # We need current_logger_dt if available
        current_logger_dt = r.date_time_last_logger
        
        # Note: average_flow calculates based on 'date_lg' passed as 3rd arg which is usually date_time_medition equivalent 
        # but in usage: average_flow(point, total, datetime_obj)
        # Let's pass r.date_time_medition
        
        try:
            new_flow = average_flow(
                point_dict, 
                float(r.total), 
                r.date_time_medition, 
                exclude_id=r.id, # Exclude self so it finds the previous one
                current_logger_dt=current_logger_dt
            )
            
            # Check if flow changed significantly (float comparison)
            if abs(float(r.flow) - new_flow) > 0.01:
                print(f"  Fixing Flow: {r.flow} -> {new_flow}")
                r.flow = new_flow
        except Exception as e:
            print(f"  Error calculating flow: {e}")

        r.save()
        updated_count += 1
            
    print(f"Process complete. Updated {updated_count} records.")

if __name__ == '__main__':
    repair_codegua_full(86)
