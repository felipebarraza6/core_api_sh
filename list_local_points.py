from api.core.models import CatchmentPoint

print("List of all local points:")
for p in CatchmentPoint.objects.all().order_by('title'):
    print(f"{p.id}: {p.title}")
