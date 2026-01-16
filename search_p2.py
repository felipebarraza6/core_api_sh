
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint

def search_broad():
    print("--- Searching 'Com' or 'P2' ---")
    points = CatchmentPoint.objects.filter(title__icontains='P2')[:20]
    for p in points:
        print(f"ID: {p.id} | Title: {p.title} | Project: {p.project.name if p.project else 'None'}")
        
    print("\n--- Searching 'Com' ---")
    points_c = CatchmentPoint.objects.filter(title__icontains='Com')
    for p in points_c:
        print(f"ID: {p.id} | Title: {p.title} | Project: {p.project.name if p.project else 'None'}")
        
    print("\n--- Searching Project 'Comasa' ---")
    from api.core.models import ProjectCatchments
    projs = ProjectCatchments.objects.filter(name__icontains='Comasa')
    for pr in projs:
        print(f"Project ID: {pr.id} | Name: {pr.name}")
        for p in pr.catchmentpoint_set.all():
             print(f"   -> Point ID: {p.id} | Title: {p.title}")

if __name__ == '__main__':
    search_broad()
