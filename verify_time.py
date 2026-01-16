
import os
import django
from django.utils import timezone
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

def check_time():
    now = timezone.now()
    local = timezone.localtime(now)
    print(f"Timezone Now (UTC): {now}")
    print(f"Local Time (Chile): {local}")
    print(f"Today Date: {local.date()}")
    
    from django.conf import settings
    print(f"TIME_ZONE setting: {settings.TIME_ZONE}")
    print(f"USE_TZ setting: {settings.USE_TZ}")

if __name__ == '__main__':
    check_time()
