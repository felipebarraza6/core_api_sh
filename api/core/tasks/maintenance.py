"""
Celery Tasks for System Maintenance (V3)
Handles cleanup, optimization, and health checks for dynamic telemetry
"""

import logging
import os
import time
from celery import shared_task
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta

from api.telemetry.models import TelemetryRecord
from api.notifications.models import NotificationResponse
from api.core.services.config_service import ConfigService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def cleanup_old_telemetry(self):
    """
    Clean up old telemetry data (V3) based on retention policy
    """
    try:
        logger.info("Starting telemetry cleanup V3")

        # Retention policy: keep 90 days of detailed data
        detailed_cutoff = timezone.now() - timedelta(days=90)

        # Delete old V3 records
        deleted_detailed, _ = TelemetryRecord.objects.filter(
            timestamp__lt=detailed_cutoff
        ).delete()

        logger.info(
            "Deleted %s old V3 telemetry records",
            deleted_detailed
        )

        # Clean up old notifications (keep 180 days)
        notification_cutoff = timezone.now() - timedelta(days=180)
        deleted_notifications, _ = (
            NotificationResponse.objects.filter(
                created__lt=notification_cutoff
            ).delete()
        )

        # Clear expired cache entries
        try:
            from api.core.cache.telemetry_cache import TelemetryCache
            TelemetryCache.clear_all_telemetry_cache()
            cache_cleared = True
        except Exception:
            logger.warning("Could not clear cache", exc_info=True)
            cache_cleared = False

        return {
            'telemetry_records_v3_deleted': deleted_detailed,
            'notifications_deleted': deleted_notifications,
            'cache_cleared': cache_cleared
        }
    except Exception as exc:
        logger.error(f"Telemetry cleanup failed: {exc}")
        self.retry(countdown=3600, exc=exc)


@shared_task(bind=True, max_retries=1)
def optimize_database_weekly(self):
    """
    Run database optimization tasks weekly
    """
    try:
        logger.info("Starting weekly database optimization")
        start_time = time.time()

        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE;")
            cursor.execute("VACUUM ANALYZE;")

        execution_time = time.time() - start_time
        logger.info(
            "Weekly database optimization completed in %.2fs",
            execution_time
        )
        return {'execution_time': execution_time, 'status': 'completed'}
    except Exception as exc:
        logger.error(
            "Weekly database optimization failed: %s",
            exc,
            exc_info=True
        )
        return {'status': 'failed', 'error': str(exc)}


@shared_task(bind=True)
def backup_database(self):
    """
    Create database backup
    """
    try:
        logger.info("Starting database backup")
        from django.conf import settings
        import shutil
        from datetime import datetime
        import gzip

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        backup_file = os.path.join(
            backup_dir,
            f'db_backup_{timestamp}.json'
        )
        with open(backup_file, 'w', encoding='utf-8') as f:
            call_command(
                'dumpdata',
                stdout=f,
                exclude=['sessions', 'admin', 'contenttypes']
            )

        compressed_file = f"{backup_file}.gz"
        with open(backup_file, 'rb') as f_in:
            with gzip.open(compressed_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        os.remove(backup_file)
        file_size = os.path.getsize(compressed_file) / (1024 * 1024)

        # Obtener número de backups a mantener desde configuración dinámica
        keep_count = ConfigService.get_int('maintenance.backup_keep_count', 7)
        cleanup_old_backups(backup_dir, keep_count)
        return {
            'backup_file': compressed_file,
            'file_size_mb': file_size,
            'status': 'completed'
        }
    except Exception as exc:
        logger.error("Database backup failed: %s", exc, exc_info=True)
        return {'status': 'failed', 'error': str(exc)}


def cleanup_old_backups(backup_dir, keep_count=7):
    """Remove old backup files, keeping only the most recent ones."""
    try:
        import glob
        pattern = os.path.join(backup_dir, 'db_backup_*.json.gz')
        backup_files = glob.glob(pattern)
        backup_files.sort(key=os.path.getmtime, reverse=True)
        files_to_remove = backup_files[keep_count:]
        for old_file in files_to_remove:
            os.remove(old_file)
    except Exception:
        logger.error("Error cleaning up old backups", exc_info=True)
