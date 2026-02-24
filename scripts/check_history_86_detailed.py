
import os
import django
import sys
from datetime import datetime

# Setup Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def check_history_detailed(point_id):
    print(f"Checking DETAILED history for Point {point_id}...")
    
    # We saw 28222 total on Feb 1st.
    # We saw 316889 pulses on Feb 6th.
    # On Feb 1st, Pulses were 282224.
    # 282224 pulses -> 28222 total.
    # This implies factor = 100 on Feb 1st too.
    # (282224 * 100) / 1000 = 28222.4 -> 28222.
    
    # So the calculation was ALWAYS consistent with factor 100.
    
    # Question: When did pulses jump from ~282224 to ~316xxx ?
    # Let's find the jump in pulses.
    
    records = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte='2026-01-25'
    ).order_by('date_time_medition')
    
    prev_pulse = None
    prev_total = None
    
    for r in records:
        curr_pulse = r.pulses
        curr_total = r.total
        
        if prev_pulse is not None:
            diff_p = curr_pulse - prev_pulse
            # Only print if significantly interesting
            if diff_p > 1000 or diff_p < -1000:
                print(f"JUMP FOUND! Date: {r.date_time_medition}")
                print(f"  Prev Pulse: {prev_pulse} -> Curr Pulse: {curr_pulse} (Diff: {diff_p})")
                print(f"  Prev Total: {prev_total} -> Curr Total: {curr_total}")
                
        prev_pulse = curr_pulse
        prev_total = curr_total

if __name__ == '__main__':
    check_history_detailed(86)
