
import os
import django
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def check_last_record():
    pid = 87
    today = timezone.localtime(timezone.now()).date()
    yesterday = today - timedelta(days=1)
    
    print(f"--- Last Record of Yesterday ({yesterday}) for Point {pid} ---")
    
    last_rec = InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__date=yesterday
    ).order_by('-date_time_medition').first()
    
    if last_rec:
        print(f"Time: {last_rec.date_time_medition}")
        print(f"Total Diff (Cleaned?): {last_rec.total_diff}")
        print(f"Total Today Diff (Running Total): {last_rec.total_today_diff}")
    else:
        print("No records found for yesterday.")

if __name__ == '__main__':
    check_last_record()
