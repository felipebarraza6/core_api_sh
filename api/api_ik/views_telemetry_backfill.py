"""
Endpoint de Backfill Histórico On-Demand
=========================================

POST /api/ik/telemetry/backfill/

Consulta datos históricos de providers (TWIN/NOVUS) para un punto y rango,
guarda en BD con update_or_create, y aplica procesamiento unificado completo:
- Totales en cascada (con base del registro anterior)
- Caudal convertido a L/s (instantaneous_flow)
- Nivel con offset + water_table (nivel_mt)
- Caudal promedio (average_flow) si aplica
- Recálculo de diffs

El backfill utiliza la configuración dinámica del TelemetryProvider asociado
al punto o a sus variables, con fallback a los booleanos legacy.

Seguridad:
- Auth requerida (Token)
- Rate limit: 5/min por usuario
- Solo staff o owner/viewer del punto pueden ejecutar
- Rango máximo: 30 días
"""

from datetime import datetime

import pytz
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from api.core.models import CatchmentPoint
from api.core.services.telemetry_backfill import (
    backfill_point_from_providers,
    get_provider_history_func,
)

from .throttles import BackfillRateThrottle


class TelemetryBackfillView(APIView):
    """
    POST /api/ik/telemetry/backfill/

    Body:
    {
        "point_id": 1,
        "start": "2026-05-19T20:00:00",
        "end": "2026-05-22T12:00:00"
    }
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [BackfillRateThrottle]
    MAX_RANGE_DAYS = 30

    def post(self, request):
        user = request.user
        data = request.data

        point_id = data.get("point_id")
        start_str = data.get("start")
        end_str = data.get("end")

        # Validaciones básicas
        if not point_id or not start_str or not end_str:
            return Response(
                {"success": False, "error": "point_id, start y end son requeridos"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            point_id = int(point_id)
        except (ValueError, TypeError):
            return Response(
                {"success": False, "error": "point_id debe ser un entero"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Parsear fechas
        chile_tz = pytz.timezone("America/Santiago")
        try:
            start_dt = chile_tz.localize(datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S"))
            end_dt = chile_tz.localize(datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            return Response(
                {"success": False, "error": "Formato de fecha inválido. Use YYYY-MM-DDTHH:MM:SS"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if end_dt <= start_dt:
            return Response(
                {"success": False, "error": "end debe ser mayor que start"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if (end_dt - start_dt).days > self.MAX_RANGE_DAYS:
            return Response(
                {"success": False, "error": f"Rango máximo permitido: {self.MAX_RANGE_DAYS} días"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar que el punto existe
        try:
            point = CatchmentPoint.objects.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response(
                {"success": False, "error": f"Punto {point_id} no existe"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verificar permisos
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

        # Verificar que el punto tenga al menos una variable con histórico soportado
        handler_name, history_func, _ = get_provider_history_func(point)
        if not history_func:
            return Response(
                {"success": False, "error": "El punto no usa un provider con soporte de histórico (TWIN o NOVUS)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ejecutar backfill + procesamiento completo
        try:
            result = backfill_point_from_providers(
                point, start_dt, end_dt, dry_run=False
            )

            processing = result.get("processing") or {}

            return Response({
                "success": True,
                "point_id": point_id,
                "point_name": point.title,
                "range": f"{start_str} → {end_str}",
                "records_created": result["records_created"],
                "records_updated": result["records_updated"],
                "records_failed": result["records_failed"],
                "processing": {
                    "totals_updated": processing.get("totals_updated", 0),
                    "flow_updated": processing.get("flow_updated", 0),
                    "nivel_updated": processing.get("nivel_updated", 0),
                    "avg_flow_updated": processing.get("avg_flow_updated", 0),
                    "total_diff_updated": processing.get("diff_updated", 0),
                    "total_today_diff_updated": processing.get("today_diff_updated", 0),
                },
                "details": {
                    "provider": result.get("provider") or handler_name,
                }
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({
                "success": False,
                "error": str(e),
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                "success": False,
                "error": str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
