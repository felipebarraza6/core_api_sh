from api.core.models import InteractionDetail
count = InteractionDetail.objects.filter(date_time_medition__year=2025, date_time_medition__month=1).count()
print(f"Jan 2025 Count: {count}")
