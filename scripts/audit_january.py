
import os
import django
import sys
from datetime import datetime
import pytz

sys.path.append('/app')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint
from django.db.models import Sum, Count

def audit_january():
    print("=== AUDIT JANUARY 2026: TELEMETRY CONSISTENCY ===")
    
    # 1. Get active points (Telemetry ON)
    points = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True,
        # Opcional: filtrar solo activos
    ).distinct()
    
    print(f"Total Points with Telemetry Configured: {points.count()}")
    
    chile_tz = pytz.timezone("America/Santiago")
    start_date = datetime(2026, 1, 1, tzinfo=chile_tz)
    end_date = datetime(2026, 2, 1, tzinfo=chile_tz)
    
    issues_found = 0
    
    for point in points:
        print(f"\nProcessing Point {point.id} ({point.title})...")
        
        # Get January records
        records = InteractionDetail.objects.filter(
            catchment_point_id=point.id,
            date_time_medition__range=(start_date, end_date)
        ).order_by('date_time_medition')
        
        if not records.exists():
            print(f"  [INFO] No records in January 2026.")
            continue
            
        # Check specific issues
        
        # 1. Zero Totals with Pulses > 0
        zeros = records.filter(total__in=['0', '0.0', '0.00'], pulses__gt=0).count()
        if zeros > 0:
            print(f"  [CRITICAL] Found {zeros} records with Total=0 but Pulses>0.")
            issues_found += 1
            
        # 2. Monotonicity (Total checks)
        # Iterate to check if total drops without reset logic triggered
        # This is expensive so we'll just check a sample or aggregate logic if possible.
        # Let's do a simple check: specific problematic days
        
        prev_total = -1
        drops = 0
        jumps = 0
        
        # Check first and last to see consumption
        first = records.first()
        last = records.last()
        try:
            consumption = float(last.total) - float(first.total)
            print(f"  [INFO] Consumption Jan: {consumption:.2f} m3 ({first.total} -> {last.total})")
            
            if consumption < 0:
                 print(f"  [WARNING] Negative consumption for month!")
                 issues_found += 1
        except (ValueError, TypeError):
             print(f"  [ERROR] Invalid total values: {first.total} -> {last.total}")
        
        # Detailed loop for drops/jumps
        # Limit to check only major issues
        for r in records:
            try:
                curr = float(r.total)
                if prev_total != -1:
                    diff = curr - prev_total
                    if diff < -100: # Allow small corrections, flag big drops
                         print(f"  [WARNING] Big Drop detected at {r.date_time_medition}: {prev_total} -> {curr} ({diff})")
                         drops += 1
                    elif diff > 500: # Massive Jump check
                         print(f"  [WARNING] Massive Jump detected at {r.date_time_medition}: {prev_total} -> {curr} ({diff})")
                         jumps += 1
                prev_total = curr
            except:
                continue
                
        if drops > 0:
            print(f"  [SUMMARY] Total Drops Detected: {drops}")
            issues_found += 1
        if jumps > 0:
            print(f"  [SUMMARY] Total Jumps Detected: {jumps}")
            # Jumps usually blocked now, so finding them means they passed or are historic
            
    print(f"\n=== AUDIT COMPLETE ===")
    print(f"Total Points Audited: {points.count()}")
    print(f"Total Issues Flagged: {issues_found}")

if __name__ == "__main__":
    audit_january()
