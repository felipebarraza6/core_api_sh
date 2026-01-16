
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def delete_bad():
    try:
        r = InteractionDetail.objects.get(id=1687540)
        r.delete()
        print("✅ Deleted bad record 1687540 (date_time_medition=None).")
    except InteractionDetail.DoesNotExist:
        print("Record already deleted.")

if __name__ == '__main__':
    delete_bad()
