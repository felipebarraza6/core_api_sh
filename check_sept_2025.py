from api.core.models import InteractionDetail
count = InteractionDetail.objects.filter(date_time_medition__year=2025, date_time_medition__month=9).count()
print(f"Sept 2025 Count: {count}")
