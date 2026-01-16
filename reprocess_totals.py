import os
import django
from django.db.models import F

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import Variable, InteractionDetail

def reprocess_history():
    print("--- Reprocessing Historical Data (Total from Pulses) ---")
    
    # We want to reprocess ALL variables that historically had an addition problem.
    # Since we already reset them to 0, we can't filter by addition > 0.
    # However, we should reprocess ALL totalizer variables to be safe, OR rely on a list if we had saved it.
    # Given the user's instruction "reprocesa los datos para atras desde que existe adicion", likely implies covering all affected points.
    # Since I don't have the explicit list of IDs saved in a file readable by this script easily without parsing,
    # and reprocessing is relatively safe if addition is now 0 (it just re-affirms total = pulses * factor),
    # I will target variables of type 'TOTALIZADO'.
    
    # Or, to be more precise, I should target variables that HAVE pulses_factor.
    variables = Variable.objects.filter(type_variable='TOTALIZADO')
    
    count_vars = variables.count()
    print(f"Found {count_vars} totalizer variables to check.")
    
    total_records_updated = 0
    
    for v in variables:
        scheme = v.scheme_catchment
        points = scheme.points_catchment.all()
        
        factor = float(v.pulses_factor or 1000)
        addition = v.addition or 0 
        # Note: addition is likely 0 now because we reset it. 
        # The goal is to apply this 0 to history, overwriting the old "doubled" totals.
        
        for p in points:
            print(f"Processing Point: {p.title} (Variable: {v.str_variable}, ID: {v.id})")
            
            # Fetch records with pulses
            records = InteractionDetail.objects.filter(
                catchment_point=p,
                pulses__isnull=False
            )
            
            # Update strategy: Bulk update?
            # We need to calculate total = (pulses * factor / 1000) + addition
            # Since factor is constant for the variable, we can do an F-expression update?
            # Issue: 'total' is a CharField in model (weird but true), but F() expressions work best on numbers.
            # Let's check model definition again... total is CharField. This complicates F() updates.
            # We must iterate and save, or cast.
            
            # Given potentially large history, iterating might be slow.
            # But 'total' being CharField is risky for direct math.
            # Let's try to update using Python loop for safety on CharField, but limit to recent history if too slow?
            # User said "reprocesa los datos para atras".
            
            # Optimization: Fetch only records where current total differs from expected total?
            # calculated = (r.pulses * factor / 1000) + addition
            # if r.total != str(calculated): update
            
            batch = []
            for r in records.iterator(): # Use iterator for memory
                try:
                    p_val = float(r.pulses)
                    expected_val = (p_val * factor) / 1000.0 + addition
                    expected_int = int(round(expected_val))
                    
                    current_total = 0
                    try:
                        current_total = int(float(r.total))
                    except (ValueError, TypeError):
                        pass
                    
                    if current_total != expected_int:
                        r.total = str(expected_int)
                        batch.append(r)
                        
                    if len(batch) >= 1000:
                        InteractionDetail.objects.bulk_update(batch, ['total'])
                        total_records_updated += len(batch)
                        batch = []
                        print(f"  - Updated {total_records_updated} records so far...")
                        
                except Exception as e:
                    print(f"Error processing record {r.id}: {e}")
            
            if batch:
                InteractionDetail.objects.bulk_update(batch, ['total'])
                total_records_updated += len(batch)

    print(f"Reprocessing complete. Total records updated: {total_records_updated}")

if __name__ == "__main__":
    reprocess_history()
