
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint

def find_comasa():
    print("--- Finding Comasa Points ---")
    points = CatchmentPoint.objects.filter(title__icontains='Comasa')
    for p in points:
        print(f"ID: {p.id} | Title: {p.title}")

if __name__ == '__main__':
    find_comasa()
