"""
Raw SQL queries for ultra-high performance telemetry operations
Use these when Django ORM becomes a bottleneck
"""

from django.db import connection
from django.utils import timezone
from datetime import timedelta
from typing import List, Dict, Optional
import json


class RawTelemetryQueries:
    """Raw SQL queries for maximum performance"""

    @staticmethod
    def get_latest_telemetry_raw(point_ids: List[int], hours_back: int = 24) -> Dict[str, Dict]:
        """
        Get latest telemetry using raw SQL - fastest possible method
        """
        if not point_ids:
            return {}

        time_threshold = timezone.now() - timedelta(hours=min(hours_back, 168))

        query = """
        WITH latest_records AS (
            SELECT DISTINCT ON (cp.id)
                id.id, id.catchment_point_id, id.date_time_medition,
                id.total, id.total_diff, id.flow, id.nivel, id.is_error, id.send_dga,
                cp.title as point_title,
                p.name as project_name,
                c.name as client_name
            FROM core_interactiondetail id
            JOIN core_catchmentpoint cp ON id.catchment_point_id = cp.id
            LEFT JOIN core_projectcatchments p ON cp.project_id = p.id
            LEFT JOIN core_client c ON p.client_id = c.id
            WHERE cp.id = ANY(%s)
              AND id.date_time_medition >= %s
            ORDER BY cp.id, id.date_time_medition DESC
        )
        SELECT
            catchment_point_id,
            json_build_object(
                'point_info', json_build_object(
                    'id', catchment_point_id,
                    'title', point_title,
                    'project', project_name,
                    'client', client_name
                ),
                'latest', json_build_object(
                    'id', id,
                    'date_time_medition', date_time_medition,
                    'total', total,
                    'total_diff', total_diff,
                    'flow', flow,
                    'nivel', nivel,
                    'is_error', is_error,
                    'send_dga', send_dga
                )
            ) as data
        FROM latest_records
        """

        with connection.cursor() as cursor:
            cursor.execute(query, [point_ids, time_threshold])
            rows = cursor.fetchall()

        result = {}
        for row in rows:
            point_id, data = row
            result[str(point_id)] = json.loads(data)

        return result

    @staticmethod
    def get_telemetry_stats_raw(point_ids: List[int], days_back: int = 30) -> Dict[str, Dict]:
        """
        Get aggregated stats using raw SQL - single query, maximum performance
        """
        if not point_ids:
            return {}

        time_threshold = timezone.now() - timedelta(days=min(days_back, 365))

        query = """
        SELECT
            catchment_point_id,
            json_build_object(
                'total_consumption', COALESCE(SUM(total_diff), 0),
                'record_count', COUNT(*),
                'last_record', MAX(date_time_medition),
                'avg_flow', AVG(flow),
                'max_flow', MAX(flow),
                'error_count', COUNT(*) FILTER (WHERE is_error = true),
                'dga_pending_count', COUNT(*) FILTER (WHERE send_dga = true),
                'period_days', %s,
                'efficiency_score', CASE
                    WHEN COUNT(*) > 0
                    THEN LEAST(95.0, 100.0 - (COUNT(*) FILTER (WHERE is_error = true)::float / COUNT(*)::float * 100.0))
                    ELSE 0.0
                END
            ) as stats
        FROM core_interactiondetail
        WHERE catchment_point_id = ANY(%s)
          AND date_time_medition >= %s
        GROUP BY catchment_point_id
        """

        with connection.cursor() as cursor:
            cursor.execute(query, [days_back, point_ids, time_threshold])
            rows = cursor.fetchall()

        result = {}
        for row in rows:
            point_id, stats = row
            result[str(point_id)] = json.loads(stats)

        return result

    @staticmethod
    def get_bulk_telemetry_raw(
        point_ids: List[int],
        hours_back: int = 24,
        limit_per_point: int = 100
    ) -> Dict[str, List[Dict]]:
        """
        Get bulk telemetry records for analysis - optimized for large datasets
        """
        if not point_ids:
            return {}

        time_threshold = timezone.now() - timedelta(hours=min(hours_back, 168))

        query = """
        SELECT
            catchment_point_id,
            json_agg(
                json_build_object(
                    'id', id,
                    'timestamp', date_time_medition,
                    'total', total,
                    'consumption', total_diff,
                    'flow', flow,
                    'level', nivel,
                    'error', is_error
                ) ORDER BY date_time_medition DESC
            ) as records
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY catchment_point_id ORDER BY date_time_medition DESC) as rn
            FROM core_interactiondetail
            WHERE catchment_point_id = ANY(%s)
              AND date_time_medition >= %s
        ) ranked
        WHERE rn <= %s
        GROUP BY catchment_point_id
        """

        with connection.cursor() as cursor:
            cursor.execute(query, [point_ids, time_threshold, limit_per_point])
            rows = cursor.fetchall()

        result = {}
        for row in rows:
            point_id, records = row
            result[str(point_id)] = json.loads(records) if records else []

        return result

    @staticmethod
    def get_error_summary_raw(hours_back: int = 24) -> Dict[str, int]:
        """
        Get error summary across all points - fast aggregation
        """
        time_threshold = timezone.now() - timedelta(hours=hours_back)

        query = """
        SELECT
            COUNT(*) as total_errors,
            COUNT(DISTINCT catchment_point_id) as points_with_errors,
            AVG(CASE WHEN is_error THEN 1 ELSE 0 END) * 100 as error_rate_percent
        FROM core_interactiondetail
        WHERE date_time_medition >= %s
        """

        with connection.cursor() as cursor:
            cursor.execute(query, [time_threshold])
            row = cursor.fetchone()

        return {
            'total_errors': row[0] or 0,
            'points_with_errors': row[1] or 0,
            'error_rate_percent': round(float(row[2] or 0), 2)
        }

    @staticmethod
    def get_performance_metrics_raw() -> Dict[str, float]:
        """
        Get database performance metrics
        """
        queries = {
            'total_records': "SELECT COUNT(*) FROM core_interactiondetail",
            'records_last_24h': """
                SELECT COUNT(*) FROM core_interactiondetail
                WHERE date_time_medition >= NOW() - INTERVAL '24 hours'
            """,
            'error_rate': """
                SELECT AVG(CASE WHEN is_error THEN 1.0 ELSE 0.0 END) * 100
                FROM core_interactiondetail
                WHERE date_time_medition >= NOW() - INTERVAL '24 hours'
            """,
            'avg_records_per_point': """
                SELECT AVG(record_count) FROM (
                    SELECT COUNT(*) as record_count
                    FROM core_interactiondetail
                    WHERE date_time_medition >= NOW() - INTERVAL '24 hours'
                    GROUP BY catchment_point_id
                ) counts
            """
        }

        results = {}
        with connection.cursor() as cursor:
            for metric_name, query in queries.items():
                try:
                    cursor.execute(query)
                    result = cursor.fetchone()[0]
                    results[metric_name] = float(result) if result is not None else 0.0
                except Exception as e:
                    results[metric_name] = 0.0

        return results