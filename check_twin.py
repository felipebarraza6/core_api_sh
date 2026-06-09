from api.core.models import CatchmentPoint
point = CatchmentPoint.objects.get(id=1)
print("Point:", point.title)
print("Frecuency:", point.frecuency)
print("Telemetry provider:", point.telemetry_provider_id)
