import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()
from api.core.models import CatchmentPoint
point = CatchmentPoint.objects.get(id=1)
print("Point:", point.title)
print("Is TWIN:", getattr(point, 'is_twin', 'N/A'))
print("Frecuency:", point.frecuency)
