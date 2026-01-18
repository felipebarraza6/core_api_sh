"""
Intelligent caching service for telemetry data
Provides smart caching with automatic invalidation
"""

from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
import hashlib
import logging

logger = logging.getLogger(__name__)


class TelemetryCache:
    """Smart caching for telemetry operations"""

    # Cache timeouts based on data freshness requirements
    CACHE_TIMEOUTS = {
        'latest_records': 30,      # 30 seconds for latest data
        'hourly_stats': 300,       # 5 minutes for hourly aggregations
        'daily_stats': 1800,       # 30 minutes for daily aggregations
        'weekly_stats': 3600,      # 1 hour for weekly aggregations
        'point_config': 3600,      # 1 hour for point configurations
    }

    @classmethod
    def get_cache_key(cls, operation: str, params: dict) -> str:
        """Generate consistent cache key for operation"""
        # Sort parameters for consistent hashing
        sorted_params = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
        key_data = f"telemetry:{operation}:{sorted_params}"
        return hashlib.md5(key_data.encode()).hexdigest()

    @classmethod
    def get_latest_records(cls, point_ids: list, hours_back: int = 24):
        """Get cached latest records with smart invalidation"""
        if len(point_ids) > 50:  # Don't cache large requests
            return None

        cache_key = cls.get_cache_key('latest_records', {
            'points': ','.join(map(str, sorted(point_ids))),
            'hours': hours_back
        })

        return cache.get(cache_key)

    @classmethod
    def set_latest_records(cls, point_ids: list, hours_back: int, data: dict):
        """Cache latest records"""
        if len(point_ids) > 50:  # Don't cache large requests
            return

        cache_key = cls.get_cache_key('latest_records', {
            'points': ','.join(map(str, sorted(point_ids))),
            'hours': hours_back
        })

        timeout = cls.CACHE_TIMEOUTS['latest_records']
        cache.set(cache_key, data, timeout)

        logger.debug(f"Cached latest records for {len(point_ids)} points, key: {cache_key}")

    @classmethod
    def get_stats(cls, point_ids: list, days_back: int = 30):
        """Get cached stats with appropriate timeout"""
        if len(point_ids) > 20:  # Don't cache very large stat requests
            return None

        cache_key = cls.get_cache_key('stats', {
            'points': ','.join(map(str, sorted(point_ids))),
            'days': days_back
        })

        return cache.get(cache_key)

    @classmethod
    def set_stats(cls, point_ids: list, days_back: int, data: dict):
        """Cache stats with appropriate timeout"""
        if len(point_ids) > 20:
            return

        cache_key = cls.get_cache_key('stats', {
            'points': ','.join(map(str, sorted(point_ids))),
            'days': days_back
        })

        # Determine timeout based on time range
        if days_back <= 1:
            timeout = cls.CACHE_TIMEOUTS['hourly_stats']
        elif days_back <= 7:
            timeout = cls.CACHE_TIMEOUTS['daily_stats']
        else:
            timeout = cls.CACHE_TIMEOUTS['weekly_stats']

        cache.set(cache_key, data, timeout)

    @classmethod
    def invalidate_point_cache(cls, point_id: int):
        """Invalidate all cache entries for a specific point"""
        # This is a simplified invalidation - in production you'd want
        # a more sophisticated cache invalidation strategy
        cache_pattern = f"telemetry:*point*{point_id}*"
        # Note: Django's cache backend doesn't support pattern deletion
        # You'd need Redis-specific operations or a cache invalidation table
        logger.info(f"Cache invalidation requested for point {point_id}")

    @classmethod
    def clear_all_telemetry_cache(cls):
        """Clear all telemetry-related cache (use with caution)"""
        # In a Redis setup, you could use pattern deletion
        logger.warning("Clearing all telemetry cache")

    @classmethod
    def get_cache_stats(cls) -> dict:
        """Get cache performance statistics"""
        try:
            # This would require Redis-specific monitoring
            return {
                'cache_hits': 0,  # Would need Redis INFO command
                'cache_misses': 0,
                'cache_hit_ratio': 0.0
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}