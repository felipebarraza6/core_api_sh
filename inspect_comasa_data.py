import os
import django
import sys
from datetime import date

# Add the project root to sys.path
sys.path.append('/root/core_api_sh')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def inspect_data():
    # Filter for ID 77 and date 2025-12-30
    # Note: date_time_medition might be used, or just checks created date if that's what's reliable
    qs = InteractionDetail.objects.filter(
        catchment_point_id=77,
        date_time_medition__date=date(2025, 12, 30)
    ).order_by('date_time_medition')

    print(f"Found {qs.count()} records for ID 77 on 2025-12-30")
    print("-" * 120)
    print(f"{'ID':<10} | {'Medition Time':<25} | {'Logger Time':<25} | {'Total':<15} | {'Flow':<10} | {'Voltage':<10}")
    print("-" * 120)

    for item in qs:
        # Check for the specific values mentioned
        mark = ""
        if item.total in [1099819, 2199638]:
            mark = " <--- FOUND"
        
        print(f"{item.id:<10} | {str(item.date_time_medition):<25} | {str(item.date_time_last_logger):<25} | {item.total:<15} | {item.flow:<10} | {item.voltage:<10}{mark}")

if __name__ == "__main__":
    inspect_data()
