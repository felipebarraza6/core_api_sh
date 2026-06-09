"""
Endpoint de Gap Detection para un punto específico
====================================================

GET /api/ik/point/{id}/gaps/

Retorna los huecos (gaps) de telemetría detectados para un punto.
No modifica la base de datos.

Query params opcionales:
- start: YYYY-MM-DDTHH:MM:SS
- end: YYYY-MM-DDTHH:MM:SS

Si no se pasan start/end, detecta entre el primer y último registro existente.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from api.core.models import CatchmentPoint
from api.cronjobs.telemetry.controllers.backfill_processing import detect_gaps


class PointGapsView(APIView):
    """
    GET /api/ik/point/{id}/gaps/

    Retorna lista de gaps detectados para el punto.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        user = request.user

        try:
            point = CatchmentPoint.objects.get(id=id)
        except CatchmentPoint.DoesNotExist:
            return Response(
                {"success": False, "error": f"Punto {id} no existe"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Permisos
        if not (user.is_staff or user.is_superuser):
            has_access = (
                point.owner_user_id == user.id
                or point.users_viewers.filter(id=user.id).exists()
            )
            if not has_access:
                return Response(
                    {"success": False, "error": "No tienes permiso para acceder a este punto"},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Parsear fechas opcionales
        from datetime import datetime
        import pytz
        chile_tz = pytz.timezone("America/Santiago")

        start_str = request.query_params.get("start")
        end_str = request.query_params.get("end")

        start_dt = None
        end_dt = None
        if start_str and end_str:
            try:
                start_dt = chile_tz.localize(datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S"))
                end_dt = chile_tz.localize(datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S"))
            except ValueError:
                return Response(
                    {"success": False, "error": "Formato de fecha inválido. Use YYYY-MM-DDTHH:MM:SS"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        gaps = detect_gaps(point, start_dt, end_dt)

        # Resumen adicional
        total_missing = sum(g["missing_count"] for g in gaps)

        return Response({
            "success": True,
            "point_id": point.id,
            "point_name": point.title,
            "gaps_count": len(gaps),
            "total_missing_records": total_missing,
            "gaps": gaps,
        }, status=status.HTTP_200_OK)
