
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint

def list_comasa_points():
    print("--- Listing Points for Project Comasa (ID 22) ---")
    points = CatchmentPoint.objects.filter(project_id=22)
    for p in points:
        print(f"ID: {p.id} | Title: {p.title}")

if __name__ == '__main__':
    list_comasa_points()
