"""
Telemetry Business Logic Service
Centralizes all telemetry-related business logic outside of serializers and views
"""

import logging
from datetime import timedelta
from typing import Dict, List, Optional

from django.db import models
from django.db.models import Avg, Count, Max, Min, Prefetch, Q, Sum
from django.utils import timezone

from api.core.cache.telemetry_cache import TelemetryCache
from api.telemetry.models.catchment_points import (
    CatchmentPoint,
    ProfileDataConfigCatchment,
)
from api.telemetry.models.telemetry import TelemetryRecord
# Notification model moved to api.notifications
from api.notifications.models import Notification

logger = logging.getLogger(__name__)


class TelemetryService:
    """Service for telemetry business logic operations"""

    @staticmethod
    def get_optimized_queryset(base_queryset=None, with_related=True):
        """Get optimized queryset with proper select_related and prefetch_related"""
        queryset = base_queryset or TelemetryRecord.objects.all()

        if with_related:
            queryset = queryset.select_related(
                "point", "point__project", "point__project__client"
            ).prefetch_related(
                Prefetch(
                    "point__data_config_profiles",
                    queryset=ProfileDataConfigCatchment.objects.only(
                        "point_catchment_id", "d6", "is_telemetry"
                    ),
                )
            )

        return queryset

    @staticmethod
    def get_latest_records_for_points(
        point_ids: List[int], hours_back: int = 24, include_inactive: bool = False
    ) -> Dict[int, Optional[TelemetryRecord]]:
        """
        Get latest telemetry record for each point using optimized query
        """
        if not point_ids:
            return {}

        if len(point_ids) > 100:
            raise ValueError("Maximum 100 points per request")

        time_threshold = timezone.now() - timedelta(hours=min(hours_back, 168))

        latest_records = (
            TelemetryService.get_optimized_queryset()
            .filter(point_id__in=point_ids, timestamp__gte=time_threshold)
            .order_by("point_id", "-timestamp")
            .distinct("point_id")
        )

        result = {}
        for record in latest_records:
            result[record.point_id] = record

        if include_inactive:
            for pid in point_ids:
                if pid not in result:
                    result[pid] = None

        return result

    @staticmethod
    def get_batch_telemetry_data(
        point_ids: List[int], hours_back: int = 24, user=None
    ) -> Dict[str, Dict]:
        """
        Get comprehensive telemetry data for multiple points
        Returns optimized structure for frontend consumption
        """
        if not point_ids or len(point_ids) > 100:
            raise ValueError("point_ids required (max 100)")

        # Try cache first (only for reasonable sizes)
        if len(point_ids) <= 50:
            cached_result = TelemetryCache.get_latest_records(point_ids, hours_back)
            if cached_result:
                logger.debug(f"Cache hit for {len(point_ids)} points")
                return cached_result

        # Get latest records
        latest_records = TelemetryService.get_latest_records_for_points(
            point_ids, hours_back, include_inactive=True
        )

        # Get point info efficiently
        points_info = TelemetryService._get_points_info_batch(point_ids)

        result = {}
        for point_id in point_ids:
            point = points_info.get(point_id)
            if not point:
                continue

            record = latest_records.get(point_id)

            result[str(point_id)] = {
                "point_info": {
                    "id": point.id,
                    "title": point.title,
                    "project": point.project.name if point.project else None,
                    "client": (
                        point.project.client.name
                        if point.project and point.project.client
                        else None
                    ),
                },
                "latest": (
                    TelemetryService._format_record_data(record, point)
                    if record
                    else None
                ),
                "no_data_reason": (
                    None if record else f"No records in last {hours_back} hours"
                ),
            }

        # Cache result for future requests
        if len(point_ids) <= 50:
            TelemetryCache.set_latest_records(point_ids, hours_back, result)

        return result

    @staticmethod
    def get_aggregated_stats(
        point_ids: List[int], days_back: int = 30
    ) -> Dict[str, Dict]:
        """
        Get aggregated statistics for multiple points using efficient SQL aggregation
        """
        if not point_ids or len(point_ids) > 50:
            raise ValueError("point_ids required (max 50)")

        # Try cache first
        cached_result = TelemetryCache.get_stats(point_ids, days_back)
        if cached_result:
            logger.debug(f"Cache hit for stats of {len(point_ids)} points")
            return cached_result

        time_threshold = timezone.now() - timedelta(
            days=min(days_back, 365)
        )  # Max 1 year

        # Single efficient aggregation query
        stats = (
            TelemetryRecord.objects.filter(
                point_id__in=point_ids, timestamp__gte=time_threshold
            )
            .values("point_id")
            .annotate(
                total_consumption=Sum("data__total_diff"),
                record_count=Count("id"),
                last_record=Max("timestamp"),
                avg_flow=Avg("data__flow"),
                max_flow=Max("data__flow"),
                error_count=Count("id", filter=Q(is_error=True)),
                dga_pending_count=Count("id", filter=Q(compliance_status__dga__sent=False)),
            )
        )

        result = {}
        for stat in stats:
            result[str(stat["point_id"])] = {
                "total_consumption": float(stat["total_consumption"] or 0),
                "record_count": stat["record_count"] or 0,
                "last_record": (
                    stat["last_record"].isoformat() if stat["last_record"] else None
                ),
                "avg_flow": float(stat["avg_flow"] or 0),
                "max_flow": float(stat["max_flow"] or 0),
                "error_count": stat["error_count"] or 0,
                "dga_pending_count": stat["dga_pending_count"] or 0,
                "period_days": days_back,
                "efficiency_score": TelemetryService._calculate_efficiency_score(stat),
            }

        # Cache result
        TelemetryCache.set_stats(point_ids, days_back, result)

        return result

    @staticmethod
    def get_points_with_recent_data(
        hours_back: int = 24, limit: int = 1000
    ) -> models.QuerySet:
        """
        Get points that have recent telemetry data
        """
        time_threshold = timezone.now() - timedelta(hours=hours_back)

        return (
            CatchmentPoint.objects.filter(telemetry_v3__timestamp__gte=time_threshold)
            .distinct()
            .select_related("project", "project__client", "owner_user")[:limit]
        )

    @staticmethod
    def validate_user_access_to_points(user, point_ids: List[int]) -> List[int]:
        """
        Validate and filter points user has access to
        Returns filtered list of accessible point IDs
        """
        if user.is_staff:
            return point_ids

        # Get user's accessible points
        accessible_points = set(
            CatchmentPoint.objects.filter(
                Q(owner_user=user) | Q(users_viewers=user)
            ).values_list("id", flat=True)
        )

        return [pid for pid in point_ids if pid in accessible_points]

    @staticmethod
    def _get_points_info_batch(point_ids: List[int]) -> Dict[int, CatchmentPoint]:
        """Get point info efficiently for multiple points"""
        points = CatchmentPoint.objects.filter(id__in=point_ids).select_related(
            "project", "project__client"
        )

        return {point.id: point for point in points}

    @staticmethod
    def _format_record_data(record: TelemetryRecord, point: CatchmentPoint) -> Dict:
        """Format record data consistently"""
        data = record.data
        return {
            "id": record.id,
            "date_time_medition": (
                record.timestamp.isoformat() if record.timestamp else None
            ),
            "date_time_last_logger": record.metadata.get("last_logger_timestamp"),
            "total": float(data.get("total", 0)),
            "total_diff": float(data.get("total_diff", 0)),
            "total_today_diff": float(data.get("total_today_diff", 0)),
            "flow": float(data.get("flow", data.get("caudal", 0))),
            "nivel": float(data.get("nivel", 0)),
            "water_table": float(data.get("water_table", 0)),
            "is_error": record.is_error,
            "compliance_status": record.compliance_status,
            "days_not_conection": record.metadata.get("days_not_connection", 0),
            "is_partial": record.is_partial,
            "pulses": data.get("pulses", 0),
        }

    @staticmethod
    def _calculate_efficiency_score(stats: Dict) -> float:
        """Calculate efficiency score based on telemetry health"""
        try:
            total_records = stats.get("record_count", 0)
            if total_records == 0:
                return 0.0

            error_rate = (stats.get("error_count", 0) / total_records) * 100
            # Efficiency = 100 - error_rate (capped at 95 for safety)
            return min(95.0, 100.0 - error_rate)
        except:
            return 0.0
