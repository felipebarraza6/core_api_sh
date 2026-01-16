from django.db.models.functions import TruncMonth
from django.db.models import Count
from api.core.models import InteractionDetail, CatchmentPoint, Variable

print("Checking CatchmentPoints...")
points_count = CatchmentPoint.objects.count()
print(f"Total CatchmentPoints: {points_count}")

print("Checking Variables...")
vars_count = Variable.objects.count()
print(f"Total Variables: {vars_count}")

print("\nChecking InteractionDetail counts by month for 2025 and 2026...")

# Filter for 2025 and 2026
details = InteractionDetail.objects.filter(
    date_time_medition__year__gte=2025
).annotate(
    month=TruncMonth('date_time_medition')
).values('month').annotate(
    count=Count('id')
).order_by('month')

if not details:
    print("No InteractionDetail records found for 2025 or 2026.")
else:
    for entry in details:
        print(f"{entry['month']}: {entry['count']} records")

# Check for latest record
last_record = InteractionDetail.objects.order_by('-date_time_medition').first()
if last_record:
    print(f"\nLast record timestamp: {last_record.date_time_medition}")
else:
    print("\nNo records found at all.")
