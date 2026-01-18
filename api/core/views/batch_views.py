"""
Batch API Views for optimized multi-resource fetching.

These endpoints reduce frontend round-trips by allowing batch requests
for multiple resources in a single API call.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

from api.telemetry.services.telemetry_service import TelemetryService


class BatchTelemetryView(APIView):
    """
    Batch endpoint para obtener telemetría de múltiples puntos de captación.

    POST /api/batch/telemetry/
    Body: { "point_ids": [1, 2, 3], "hours": 1 }

    Returns: {
        "1": { "latest": {...}, "stats": {...} },
        "2": { "latest": {...}, "stats": {...} },
        ...
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        point_ids = request.data.get('point_ids', [])
        hours_back = request.data.get('hours', 1)

        if not point_ids:
            return Response(
                {"error": "point_ids is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(point_ids) > 100:  # Increased from 50 for better batching
            return Response(
                {"error": "Maximum 100 points per request"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate user has access to requested points
        point_ids = TelemetryService.validate_user_access_to_points(request.user, point_ids)

        if not point_ids:
            return Response({"data": {}})

        # Use optimized service method
        try:
            result = TelemetryService.get_batch_telemetry_data(point_ids, hours_back, request.user)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        now = timezone.now()
        return Response({
            "data": result,
            "meta": {
                "requested": len(request.data.get('point_ids', [])),
                "returned": len(result),
                "time_window_hours": hours_back,
                "timestamp": now.isoformat()
            }
        })


class BatchStatsView(APIView):
    """
    Batch endpoint para estadísticas agregadas de múltiples puntos.

    POST /api/batch/stats/
    Body: { "point_ids": [1, 2, 3], "days": 30 }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        point_ids = request.data.get('point_ids', [])
        days_back = request.data.get('days', 30)

        if not point_ids or len(point_ids) > 50:
            return Response(
                {"error": "point_ids required (max 50)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate user access
        point_ids = TelemetryService.validate_user_access_to_points(request.user, point_ids)

        if not point_ids:
            return Response({"data": {}})

        # Use optimized service method
        try:
            result = TelemetryService.get_aggregated_stats(point_ids, days_back)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"data": result})
