
import os
import django
import sys

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def repair_jump_records(point_id):
    # Fix 12:00 and 13:00 records which were skipped or have old total
    # 13:00 Record: Pulses: 314662 | Total: 28222 -> Should be ~31466
    
    records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__in=['2026-02-05 12:00:00', '2026-02-05 13:00:00']
    )
    
    pulses_factor = 100
    
    for r in records:
        print(f"Fixing {r.date_time_medition}...")
        
        calculated_total = (float(r.pulses) * pulses_factor) / 1000.0
        new_total_int = int(round(calculated_total))
        new_total_str = str(new_total_int)
        
        print(f"  Total: {r.total} -> {new_total_str}")
        r.total = new_total_str
        r.save()
        
    # Now recalculate Diff for 13:00 and 14:00
    # We need to fetch them again to get updated values
    
    # 1. Diff for 13:00 (vs 12:00)
    rec_12 = InteractionDetail.objects.get(catchment_point_id=point_id, date_time_medition='2026-02-05 12:00:00')
    rec_13 = InteractionDetail.objects.get(catchment_point_id=point_id, date_time_medition='2026-02-05 13:00:00')
    rec_14 = InteractionDetail.objects.get(catchment_point_id=point_id, date_time_medition='2026-02-05 14:00:00')
    
    # Check 12:00 vs previous (11:00) - Assuming 11:00 is ~28222 or we should check
    # Actually wait. If 12:00 had the JUMP in pulses.
    # 11:00 -> Pulses 282224 (Total 28222)
    # 12:00 -> Pulses 310193 (Total 31019) -> HUGE DIFF HERE (2797 m3)
    # This IS the real jump.
    
    # If the jump is REAL (restoration of connection / sensor reset?), we should keep it?
    # No, user said "no me cuadra con el esquema".
    # Usually huge jumps are glitches or resets.
    
    # IF the sensor was disconnected for 10 days (as seen in screenshot GAP: 10d), then the jump is REAL accumulated consumption.
    # 2797 m3 / 10 days = 279 m3/day = 11.6 m3/h.
    # 11.6 m3/h = 3.2 L/s.
    
    # So the average flow SHOULD be ~3.2 L/s over the gap period.
    # But the system puts it all in ONE hour (12:00).
    # This causes that specific hour to have huge flow.
    
    # BUT, the issue is "39.13 (prom)".
    # If the system calculates "MEDIO" as Daily Average, it sums all consumption in the day / 24h?
    # Or sum consumption / sum time?
    
    # If we have 2797 m3 in ONE hour, and normal consumption rest of day.
    # Total Day Consumption ~ 3000 m3.
    # Average Flow of Day = 3000 m3 / 24h = 125 m3/h = 34 L/s.
    # This matches 39.13 pretty closely.
    
    # So the "Caudal Promedio" logic is correctly calculating the average of the day INCLUDING the huge jump.
    
    # THE PROBLEM: The consumption happened over 10 days, not 1 hour.
    # We cannot fix the past 10 days of missing records easily (unless we interpolate).
    # But we can "hide" this jump from the daily average if we want to show current flow?
    # Or better: The user wants "Caudal Medio" to reflect the CURRENT status, not the distortion of the jump.
    
    # If I fix 12:00 and 13:00, the consumption of 2797 m3 will effectively appear at 12:00.
    
    # To fix "39.13" appearing for records at 11:00, 10:00 (which are today, Feb 6th!), 
    # WAIT. Why does Feb 6th records use Feb 5th average?
    # CAUDAL_PROMEDIO standard "MEDIO" usually means "Daily Average".
    # Is it "Average of the Current Day"?
    # If so, Feb 6th should depend on Feb 6th consumption.
    # Feb 6th consumption is normal (17, 16, etc).
    # So Feb 6th Average should be normal (~4 L/s).
    
    # Why is it showing 39.13?
    # Maybe because standard="MEDIO" (check_config.py output needed!) implies something else?
    # Or maybe `calculate_daily_average_flow` looks at a sliding window?
    
    # Let's fix the totals first to ensure consistnecy.
    
    # Fix 12:00 and 13:00.
    # Then update 14:00 diff.
    
    diff_13_12 = int(rec_13.total) - int(rec_12.total) # 31466 - 31019 = 447
    rec_13.total_diff = diff_13_12
    rec_13.save()
    
    diff_14_13 = int(rec_14.total) - int(rec_13.total) # 31473 - 31466 = 7
    print(f"Correcting 14:00 Diff: {rec_14.total_diff} -> {diff_14_13}")
    rec_14.total_diff = diff_14_13
    rec_14.save()
    
    # What about 12:00?
    # 12:00 Total 31019. Previous (11:00 Feb 5) Total 28222.
    # Diff = 2797.
    # This huge diff will remain at 12:00.
    
    rec_12.total_diff = int(rec_12.total) - 28222
    rec_12.save()

if __name__ == '__main__':
    repair_jump_records(86)
