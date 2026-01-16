import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail
from django.utils import timezone
import datetime

# Clean up San Carlos (ID 188)
# Remove records where second != 0 or microsecond != 0
# AND remove minutes % 10 != 0 (just in case)

now = timezone.now()
start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

records = InteractionDetail.objects.filter(
    catchment_point_id=187,
    date_time_medition__gte=start_of_day
)

print(f"Scanning {records.count()} records for ID 187 since {start_of_day}")

deleted_count = 0
for r in records:
    # Check if minute is off
    if r.date_time_medition.minute % 10 != 0:
        print(f"Deleting off-minute: {r.date_time_medition}")
        r.delete()
        deleted_count += 1
        continue
    
    # Check if seconds/micro are off
    if r.date_time_medition.second != 0 or r.date_time_medition.microsecond != 0:
        print(f"Deleting off-second: {r.date_time_medition}")
        r.delete()
        deleted_count += 1
        continue

print(f"Deleted {deleted_count} invalid records.")

# Final check for duplicates at :00
from django.db.models import Count
dups = InteractionDetail.objects.filter(
    catchment_point_id=188,
    date_time_medition__gte=start_of_day
).values('date_time_medition').annotate(count=Count('id')).filter(count__gt=1)

print(f"Remaining duplicates (exact timestamp): {dups.count()}")
for d in dups:
     print(f" - {d['date_time_medition']}: {d['count']}")
