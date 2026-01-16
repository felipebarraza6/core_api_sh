
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail

def inspect_bad_record():
    try:
        r = InteractionDetail.objects.get(id=1687540)
        print(f"ID: {r.id}")
        print(f"Date: {r.date_time_medition}")
        print(f"Created: {r.created}")
        print(f"Total: {r.total}")
        print(f"Diff: {r.total_diff}")
        print(f"Catchment Point: {r.catchment_point_id}")
    except InteractionDetail.DoesNotExist:
        print("Record not found.")

if __name__ == '__main__':
    inspect_bad_record()
