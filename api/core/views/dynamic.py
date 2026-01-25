from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from api.telemetry.models import CatchmentPoint, TelemetryRecord, CoreVariable
from django.shortcuts import get_object_or_404

class PointTelemetryDynamicView(APIView):
    """
    API Dinámica - Consulta de telemetría por punto.
    Devuelve los datos estructurados basándose en las variables configuradas.
    """

    def get(self, request, point_id):
        try:
            point = CatchmentPoint.objects.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response({"error": "Punto no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        # 1. Obtener variables configuradas para el punto
        variables = CoreVariable.objects.filter(point=point, is_active=True)
        var_map = {v.internal_code: {"name": v.name, "unit": v.unit} for v in variables}

        # 2. Obtener últimos registros (limitado a 100 por defecto)
        limit = int(request.query_params.get('limit', 100))
        records = TelemetryRecord.objects.filter(point=point).order_by('-timestamp')[:limit]

        # 3. Construir respuesta dinámica
        telemetry_data = []
        for r in records:
            # Enriquecemos el JSON con metadata si es necesario
            telemetry_data.append({
                "timestamp": r.timestamp,
                "values": r.data,
                "is_partial": r.metadata.get("partial", False)
            })

        return Response({
            "point_id": point.id,
            "point_name": point.title,
            "config": {
                "variables": var_map
            },
            "data": telemetry_data
        })

class SystemStatusDynamicView(APIView):
    """
    API Dinámica - Resumen de salud de todos los puntos.
    """
    def get(self, request):
        points = CatchmentPoint.objects.all()
        result = []
        
        for p in points:
            last_record = TelemetryRecord.objects.filter(point=p).first()
            result.append({
                "id": p.id,
                "name": p.title,
                "last_seen": last_record.timestamp if last_record else None,
                "status": "OK" if last_record and last_record.data else "OFFLINE"
            })
            
        return Response(result)
