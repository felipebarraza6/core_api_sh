
import os
import django
import sys
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail

def check_10min_telemetry():
    print("Checking for points with frequency '10'...")
    points_10m = CatchmentPoint.objects.filter(frecuency="10")
    
    if not points_10m.exists():
        print("No points found with frequency '10'.")
        return

    print(f"Found {points_10m.count()} points with frequency '10':")
    for p in points_10m:
        print(f" - ID: {p.id}, Name: {p.title}, Project: {p.project.name if p.project else 'N/A'}")

    print("\nChecking for recent InteractionDetail records (last 30 minutes)...")
    time_threshold = timezone.now() - timedelta(minutes=30)
    
    for p in points_10m:
        recent_interactions = InteractionDetail.objects.filter(
            catchment_point=p,
            created__gte=time_threshold
        ).order_by('-created')
        
        if recent_interactions.exists():
            print(f"✅ Point {p.title} (ID {p.id}): Found {recent_interactions.count()} interactions.")
            latest = recent_interactions.first()
            print(f"   Latest: {latest.created} (Flow: {latest.flow})")
        else:
            print(f"⚠️ Point {p.title} (ID {p.id}): No interactions found in the last 30 minutes.")

if __name__ == "__main__":
    check_10min_telemetry()
