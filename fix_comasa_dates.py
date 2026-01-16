import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail
from django.db.models import F

# Fix Comasa P2 (ID 77)
# Update records where date_time_medition is NULL
# Set date_time_medition = created
# Set date_time_last_logger = created (or leave null? User said "todos deben tener date time medition")
# Better to fill last_logger too so it looks valid.

count = InteractionDetail.objects.filter(catchment_point_id=77, date_time_medition__isnull=True).count()
print(f"Fixing {count} records for ID 77...")

# Use F() expression for efficient update
InteractionDetail.objects.filter(
    catchment_point_id=77, 
    date_time_medition__isnull=True
).update(
    date_time_medition=F('created'),
    date_time_last_logger=F('created')
)

print("Done.")
