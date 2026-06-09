
import os
import sys
import django

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.models import InteractionDetail

pid = 113
regs = InteractionDetail.objects.filter(catchment_point_id=pid).order_by("-date_time_medition")[:10]

print(f"{'Date':<25} | {'Pulses':<10} | {'Total':<10} | {'Diff':<10}")
print("-" * 60)
for r in regs:
    print(f"{str(r.date_time_medition):<25} | {r.pulses:<10} | {r.total:<10} | {r.total_diff:<10}")
