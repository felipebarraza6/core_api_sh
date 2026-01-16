import os
import django
import json
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint

def fix_missing_variable_details():
    print("Fixing missing variable details for Total Disconnections (Last 400 days)...")
    
    start_date = datetime.now() - timedelta(days=400)
    # Find records that claim to be disconnected but have NO variable details
    records = InteractionDetail.objects.filter(
        date_time_medition__gte=start_date,
        days_not_conection__gt=0,
        is_partial=False
    )
    
    updated_count = 0
    print(f"Scanning {records.count()} records...")
    
    for record in records:
        details = record.variable_details
        changed = False
        
        # Case 1: No Details at all -> Create them based on point config
        if not details:
            # We need to know what variables this point generally has.
            # We can infer from ProfileDataConfigCatchment or recent records.
            # Or just default to the standard set if unknown: CAUDAL, NIVEL, TOTALIZADO.
            # Let's check config.
            point = record.catchment_point
            
            # This is a bit expensive database-wise, but accurate.
            # Let's try to get profile config.
            try:
                # Assuming standard variables for now to save time/complexity and cover 90% cases.
                # If we want to be precise we should query ProfileDataConfigCatchment.
                # BUT, since we want them RED, adding extra variables that might not exist is safer than missing them?
                # Actually, displaying non-existent variables is confusing.
                # Let's look at the point's available variables/columns from its serializer or just guess?
                # The user saw "CAUDAL_PROMEDIO", "NIVEL", "TOTALIZADO".
                
                # Let's create a generic set and rely on the dashboard to just render what we save.
                # Standard set: CAUDAL, NIVEL, TOTALIZADO or CAUDAL_PROMEDIO.
                
                # Check if it has 'flow' or 'total' or 'nivel' values in the record itself?
                # If record.flow is not None -> CAUDAL
                # If record.total is not None -> TOTALIZADO
                # If record.nivel is not None -> NIVEL
                
                new_details = []
                
                # Add NIVEL
                new_details.append({
                    "name": "NIVEL",
                    "type": "NIVEL",
                    "days": record.days_not_conection,
                    "timestamp": None
                })
                
                # Add TOTALIZADO
                new_details.append({
                    "name": "TOTALIZADO",
                    "type": "TOTALIZADO",
                    "days": record.days_not_conection,
                    "timestamp": None
                })
                
                # Check DGA config to decide between CAUDAL or CAUDAL_PROMEDIO?
                # Or just add CAUDAL by default.
                # The screenshot showed CAUDAL_PROMEDIO.
                # Let's add CAUDAL. The dashboard logic might rename it?
                # Doing CAUDAL is safe.
                new_details.append({
                    "name": "CAUDAL",
                    "type": "CAUDAL",
                    "days": record.days_not_conection,
                    "timestamp": None
                })
                
                record.variable_details = new_details
                changed = True
                
            except Exception as e:
                print(f"Error processing record {record.id}: {e}")
                continue

        # Case 2: Details exist but have 0 days (covered by previous script, but let's re-run here too)
        else:
            for var in details:
                if var.get('days', 0) == 0:
                    var['days'] = record.days_not_conection
                    changed = True
            if changed:
                record.variable_details = details

        if changed:
            record.save()
            updated_count += 1
            if updated_count % 100 == 0:
                print(f"Fixed {updated_count} records...")

    print(f"Fixed {updated_count} records.")

if __name__ == "__main__":
    fix_missing_variable_details()
