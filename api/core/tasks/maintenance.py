"""
Celery Tasks for System Maintenance (V3)
Handles cleanup, optimization, and health checks for dynamic telemetry
"""

import logging
import os
import time
import psutil
from celery import shared_task
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta

from api.core.models import TelemetryRecord, NotificationsCatchment
from api.core.cache.telemetry_cache import TelemetryCache

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

        logger.info(f"Deleted {deleted_detailed} old V3 telemetry records")

        # Clean up old notifications (keep 180 days)
        notification_cutoff = timezone.now() - timedelta(days=180)
        from api.core.models import ResponseNotificationsCatchment
        deleted_notifications, _ = ResponseNotificationsCatchment.objects.filter(
            created_at__lt=notification_cutoff
        ).delete()

        # Clear expired cache entries
        TelemetryCache.clear_all_telemetry_cache()

        return {
            'telemetry_records_v3_deleted': deleted_detailed,
            'notifications_deleted': deleted_notifications,
            'cache_cleared': True
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
        logger.info(f"Weekly database optimization completed in {execution_time:.2f}s")
        return {'execution_time': execution_time, 'status': 'completed'}
    except Exception as exc:
        logger.error(f"Weekly database optimization failed: {exc}")
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

        backup_file = os.path.join(backup_dir, f'db_backup_{timestamp}.json')
        with open(backup_file, 'w') as f:
            call_command('dumpdata', stdout=f, exclude=['sessions', 'admin', 'contenttypes'])

        compressed_file = f"{backup_file}.gz"
        with open(backup_file, 'rb') as f_in:
            with gzip.open(compressed_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        os.remove(backup_file)
        file_size = os.path.getsize(compressed_file) / (1024 * 1024)
        
        cleanup_old_backups(backup_dir, 7)
        return {'backup_file': compressed_file, 'file_size_mb': file_size, 'status': 'completed'}
    except Exception as exc:
        logger.error(f"Database backup failed: {exc}")
        return {'status': 'failed', 'error': str(exc)}


def cleanup_old_backups(backup_dir, keep_count=7):
    try:
        import glob
        backup_files = glob.glob(os.path.join(backup_dir, 'db_backup_*.json.gz'))
        backup_files.sort(key=os.path.getmtime, reverse=True)
        files_to_remove = backup_files[keep_count:]
        for old_file in files_to_remove:
            os.remove(old_file)
    except Exception as exc:
        logger.error(f"Error cleaning up old backups: {exc}")
