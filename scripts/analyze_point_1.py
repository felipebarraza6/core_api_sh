import os
import django
import sys
from datetime import datetime, timedelta
import json

# Setup Django Environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail, Variable

def analyze_point_1():
    point_id = 1
    start_date = datetime(2026, 1, 1)
    end_date = datetime(2026, 2, 1) # Exclusive
    
    print(f"--- Analysis for Catchment Point {point_id} (Jan 2026) ---")

    try:
        point = CatchmentPoint.objects.get(id=point_id)
        print(f"Point: {point.title}")
        print(f"Frequency: {point.frecuency} minutes")
    except CatchmentPoint.DoesNotExist:
        print("Point not found!")
        return

    # Check Variables
    variables = Variable.objects.filter(scheme_catchment__points_catchment=point)
    print("\n--- Variables Configuration ---")
    for var in variables:
        print(f"ID: {var.id}, Type: {var.type_variable}, Label: {var.label}, Str: {var.str_variable}")

    # Fetch Data
    qs = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__range=(start_date, end_date)
    ).order_by('date_time_medition')

    total_records = qs.count()
    print(f"\nTotal Records in Jan 2026: {total_records}")

    if total_records == 0:
        print("No data found for this period.")
        return

    # Analysis Counters
    zeros_total = 0
    zeros_flow = 0
    massive_jumps = 0
    gaps = 0
    partials = 0
    
    prev_time = None
    expected_freq = int(point.frecuency) if point.frecuency else 60

    print("\n--- Data Health Scan ---")
    
    scan_limit = 5 # Print first 5 issues of each type
    jump_examples = []
    
    for record in qs:
        # Check Total Zeros
        try:
            val_total = float(record.total) if record.total else 0
            if val_total == 0:
                zeros_total += 1
        except:
            pass # Handle non-numeric total if any

        # Check Flow Zeros (Assuming flow is decimal)
        if record.flow == 0:
            zeros_flow += 1

        # Check Partials
        if record.is_partial:
            partials += 1

        # Check Massive Jumps in Details
        if record.variable_details:
            details_str = json.dumps(record.variable_details)
            if "MASSIVE_JUMP_BLOCKED" in details_str:
                massive_jumps += 1
                if len(jump_examples) < scan_limit:
                    jump_examples.append(f"{record.date_time_medition}: {details_str[:200]}...")

        # Check Gaps
        if prev_time:
            diff = (record.date_time_medition - prev_time).total_seconds() / 60
            # Allow some jitter (e.g. +5 mins tolerance)
            if diff > (expected_freq + 5):
                gaps += 1
        
        prev_time = record.date_time_medition

    print(f"Records with Total=0: {zeros_total}")
    print(f"Records with Flow=0: {zeros_flow}")
    print(f"Records with 'is_partial'=True: {partials}")
    print(f"Records with MASSIVE_JUMP_BLOCKED: {massive_jumps}")
    print(f"Time Gaps Detected (> {expected_freq} mins): {gaps}")

    if massive_jumps > 0:
        print("\n--- Specific Jump Examples ---")
        for example in jump_examples:
            print(example)

    print("\n--- End of Analysis ---")

if __name__ == "__main__":
    analyze_point_1()
