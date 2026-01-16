
import os
import django
from django.utils import timezone
from datetime import timedelta
from django.db import models

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint

def verify_batch():
    pid = 77
    print(f"--- Verifying Batch Logic for Comasa P2 (ID {pid}) ---")
    
    cp_ids = [pid]
    
    today = timezone.localtime(timezone.now()).date()
    # today = timezone.now().date() # What if it was this?
    
    print(f"Today used: {today}")
    
    # 2. Today's Records logic from UserProfile
    today_qs = InteractionDetail.objects.filter(
        catchment_point__in=cp_ids,
        date_time_medition__range=(today, timezone.now())
    ).order_by('date_time_medition')
    
    print(f"Query: {today_qs.query}")
    
    count = today_qs.count()
    print(f"Records found via Batch Logic: {count}")
    
    for r in today_qs:
        print(f" - {r.date_time_medition}")

if __name__ == '__main__':
    verify_batch()
