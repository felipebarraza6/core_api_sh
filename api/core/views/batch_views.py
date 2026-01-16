"""
Batch API Views for optimized multi-resource fetching.

These endpoints reduce frontend round-trips by allowing batch requests
for multiple resources in a single API call.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Max, Sum, F
from django.utils import timezone
from datetime import timedelta

from api.core.models import InteractionDetail, CatchmentPoint


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
        
        if len(point_ids) > 50:
            return Response(
                {"error": "Maximum 50 points per request"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate user has access to requested points
        user = request.user
        if not user.is_staff:
            # Non-staff users can only access their own points
            allowed_points = set(
                CatchmentPoint.objects.filter(
                    owner_user=user
                ).values_list('id', flat=True)
            ) | set(
                user.viewed_catchment_points.values_list('id', flat=True)
            )
            point_ids = [pid for pid in point_ids if pid in allowed_points]
        
        if not point_ids:
            return Response({"data": {}})
        
        # Calculate time window
        now = timezone.now()
        time_threshold = now - timedelta(hours=hours_back)
        
        # Single optimized query for latest records per point
        # Using subquery to get latest record ID per point
        latest_records = InteractionDetail.objects.filter(
            catchment_point_id__in=point_ids,
            date_time_medition__gte=time_threshold
        ).select_related(
            'catchment_point',
            'catchment_point__project',
            'catchment_point__project__client'
        ).order_by('catchment_point_id', '-date_time_medition').distinct('catchment_point_id')
        
        # Build response grouped by point
        result = {}
        for record in latest_records:
            cp_id = str(record.catchment_point_id)
            point = record.catchment_point
            
            result[cp_id] = {
                "point_info": {
                    "id": point.id,
                    "title": point.title,
                    "project": point.project.name if point.project else None,
                    "client": point.project.client.name if point.project and point.project.client else None,
                },
                "latest": {
                    "id": record.id,
                    "date_time_medition": record.date_time_medition.isoformat() if record.date_time_medition else None,
                    "date_time_last_logger": record.date_time_last_logger.isoformat() if record.date_time_last_logger else None,
                    "total": record.total,
                    "total_diff": record.total_diff,
                    "total_today_diff": record.total_today_diff,
                    "flow": record.flow,
                    "nivel": record.nivel,
                    "water_table": record.water_table,
                    "is_error": record.is_error,
                    "send_dga": record.send_dga,
                    "n_voucher": record.n_voucher or "-",
                }
            }
        
        # Add empty entries for points with no recent data
        for pid in point_ids:
            if str(pid) not in result:
                point = CatchmentPoint.objects.filter(id=pid).select_related(
                    'project', 'project__client'
                ).first()
                if point:
                    result[str(pid)] = {
                        "point_info": {
                            "id": point.id,
                            "title": point.title,
                            "project": point.project.name if point.project else None,
                            "client": point.project.client.name if point.project and point.project.client else None,
                        },
                        "latest": None,
                        "no_data_reason": "No records in last {} hours".format(hours_back)
                    }
        
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
        
        now = timezone.now()
        time_threshold = now - timedelta(days=days_back)
        
        # Aggregate stats per point in single query
        stats = InteractionDetail.objects.filter(
            catchment_point_id__in=point_ids,
            date_time_medition__gte=time_threshold
        ).values('catchment_point_id').annotate(
            total_consumption=Sum('total_diff'),
            record_count=Sum(F('id') * 0 + 1),  # Count trick
            last_record=Max('date_time_medition')
        )
        
        result = {str(s['catchment_point_id']): {
            "total_consumption": float(s['total_consumption'] or 0),
            "record_count": s['record_count'] or 0,
            "last_record": s['last_record'].isoformat() if s['last_record'] else None,
            "period_days": days_back
        } for s in stats}
        
        return Response({"data": result})
