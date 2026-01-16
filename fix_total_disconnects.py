import os
import django
import json
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def fix_total_disconnects():
    print("Fixing Total Disconnection consistency (Last 400 days)...")
    
    # Check last 400 days to cover records ~1 year old
    start_date = datetime.now() - timedelta(days=400)
    records = InteractionDetail.objects.filter(
        date_time_medition__gte=start_date,
        days_not_conection__gt=0,
        is_partial=False
    )
    
    updated_count = 0
    print(f"Scanning {records.count()} records...")
    
    for record in records:
        if not record.variable_details:
            continue
            
        details = record.variable_details
        changed = False
        
        # If it's a total disconnection, NO variable should be having days=0
        for var in details:
            if var.get('days', 0) == 0:
                # print(f"Record {record.id}: is_partial=False but {var['name']} is OK. Fixing.")
                var['days'] = record.days_not_conection
                changed = True
        
        if changed:
            record.variable_details = details
            record.save()
            updated_count += 1
            if updated_count % 100 == 0:
                print(f"Fixed {updated_count} records...")

    print(f"Fixed {updated_count} records.")

if __name__ == "__main__":
    fix_total_disconnects()
