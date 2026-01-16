import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint
from django.utils import timezone
import datetime

# Clean up San Carlos (ID 188)
# Remove records where minute is not a multiple of 10
# Focus on today to be safe, or last 24h
now = timezone.now()
start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

records = InteractionDetail.objects.filter(
    catchment_point_id=188,
    date_time_medition__gte=start_of_day
)

print(f"Scanning {records.count()} records for ID 188 since {start_of_day}")

deleted_count = 0
for r in records:
    minute = r.date_time_medition.minute
    if minute % 10 != 0:
        print(f"Deleting invalid record: {r.date_time_medition} (Minute {minute})")
        r.delete()
        deleted_count += 1
    else:
        # Also check for seconds/duplicates? 
        # The cron creates at :00 seconds usually.
        # If we have multiple for the same 10-min slot, keep one?
        pass

print(f"Deleted {deleted_count} invalid records.")

# Get config for Recovery
try:
    cp = CatchmentPoint.objects.get(id=188)
    # It is a ManyToMany, we usually want the one with is_telemetry=True?
    # twin_f10 filters by data_config_profiles__is_telemetry=True
    profile_relation = cp.data_config_profiles.filter(is_telemetry=True).first()
    
    if profile_relation:
        print("--- Config Object Dict ---")
        # Filter out internal state for cleaner output
        data = {k:v for k,v in profile_relation.__dict__.items() if not k.startswith('_')}
        print(data)
        
        # Also print scheme if available
        if hasattr(profile_relation, 'scheme'):
             print(f"Scheme: {profile_relation.scheme}")
        if hasattr(profile_relation, 'token_service'):
             print(f"Token: {profile_relation.token_service}")

except Exception as e:
    print(f"Error getting config: {e}")
