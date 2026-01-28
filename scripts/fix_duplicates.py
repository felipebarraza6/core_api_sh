from django.db.models import Count
from api.core.models import InteractionDetail

print("Searching for duplicates in InteractionDetail...")
# Find duplicates based on the unique_together constraint in migration 0017
duplicates = InteractionDetail.objects.values('catchment_point_id', 'date_time_medition').annotate(count=Count('id')).filter(count__gt=1)

total_deleted = 0
for dup in duplicates:
    # Get all records matching the duplicate criteria
    qs = InteractionDetail.objects.filter(
        catchment_point_id=dup['catchment_point_id'], 
        date_time_medition=dup['date_time_medition']
    ).order_by('-id') # Order by ID descending
    
    # Skip the first one (most recent ID), delete the rest
    to_delete = qs[1:] 
    
    for obj in to_delete:
        print(f"Deleting duplicate InteractionDetail ID {obj.id} (Point: {dup['catchment_point_id']}, Date: {dup['date_time_medition']})")
        obj.delete()
        total_deleted += 1

print(f"Cleanup complete. Deleted {total_deleted} duplicate records.")
