"""
Celery Tasks for System Monitoring (V3)
Provides health checks and performance monitoring for dynamic telemetry
"""

import logging
import time
import psutil
import redis
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from api.telemetry.models import TelemetryRecord, CatchmentPoint
from api.telemetry.services.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def perform_health_check(self):
    """
    Perform comprehensive system health check V3
    """
    try:
        logger.info("Starting system health check V3")

        start_time = time.time()
        health_status = {
            'timestamp': timezone.now().isoformat(),
            'services': {},
            'metrics': {},
            'alerts': []
        }

        health_status['services']['database'] = check_database_health()
        health_status['services']['redis'] = check_redis_health()
        health_status['services']['telemetry'] = check_telemetry_health()
        health_status['metrics']['system'] = get_system_metrics()
        health_status['metrics']['performance'] = get_performance_metrics()

        alerts = []
        for service, status in health_status['services'].items():
            if status.get('status') != 'healthy':
                alerts.append({
                    'type': 'service_unhealthy',
                    'service': service,
                    'details': status
                })

        system_metrics = health_status['metrics']['system']
        if system_metrics.get('cpu_percent', 0) > 80:
            alerts.append({'type': 'high_cpu_usage', 'value': system_metrics['cpu_percent'], 'threshold': 80})

        if system_metrics.get('memory_percent', 0) > 85:
            alerts.append({'type': 'high_memory_usage', 'value': system_metrics['memory_percent'], 'threshold': 85})

        health_status['alerts'] = alerts
        health_status['overall_status'] = 'healthy' if not alerts else ('warning' if len(alerts) < 3 else 'critical')

        execution_time = time.time() - start_time
        health_status['execution_time'] = execution_time

        if health_status['overall_status'] == 'critical':
            send_health_alert(health_status)

        return health_status

    except Exception as exc:
        logger.error(f"Health check failed: {exc}")
        self.retry(countdown=60, exc=exc)


def check_database_health():
    """
    Check database connectivity and V3 performance
    """
    try:
        from django.db import connection
        start_time = time.time()

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()

            # Performance test - count recent V3 records
            cursor.execute("""
                SELECT COUNT(*) FROM core_telemetryrecordv3
                WHERE timestamp >= NOW() - INTERVAL '1 hour';
            """)
            recent_count = cursor.fetchone()[0]

        return {
            'status': 'healthy',
            'query_time': time.time() - start_time,
            'recent_records_v3': recent_count
        }
    except Exception as exc:
        logger.error(f"Database health check failed: {exc}")
        return {'status': 'unhealthy', 'error': str(exc)}


def check_redis_health():
    """
    Check Redis connectivity
    """
    try:
        from django.core.cache import cache
        start_time = time.time()
        cache.set('health_check_test', 'ok', 10)
        retrieved = cache.get('health_check_test')
        cache.delete('health_check_test')

        if retrieved == 'ok':
            return {'status': 'healthy', 'response_time': time.time() - start_time}
        return {'status': 'unhealthy', 'error': 'cache inconsistency'}
    except Exception as exc:
        logger.error(f"Redis health check failed: {exc}")
        return {'status': 'unhealthy', 'error': str(exc)}


def check_telemetry_health():
    """
    Check telemetry data flow health (V3)
    """
    try:
        one_hour_ago = timezone.now() - timedelta(hours=1)

        recent_readings = TelemetryRecord.objects.filter(
            timestamp__gte=one_hour_ago
        ).count()

        error_readings = TelemetryRecord.objects.filter(
            timestamp__gte=one_hour_ago,
            is_error=True
        ).count()

        error_rate = (error_readings / recent_readings * 100) if recent_readings > 0 else 0

        active_points = CatchmentPoint.objects.filter(
            telemetry_v3__timestamp__gte=one_hour_ago
        ).distinct().count()

        status = 'healthy'
        issues = []

        if recent_readings == 0:
            status = 'critical'
            issues.append('no_recent_readings_v3')
        elif error_rate > 20:
            status = 'warning'
            issues.append('high_error_rate_v3')
        elif active_points == 0:
            status = 'critical'
            issues.append('no_active_points_v3')

        return {
            'status': status,
            'recent_readings': recent_readings,
            'error_rate': error_rate,
            'active_points': active_points,
            'issues': issues
        }
    except Exception as exc:
        logger.error(f"Telemetry health check failed: {exc}")
        return {'status': 'unhealthy', 'error': str(exc)}


def get_system_metrics():
    """
    Get system resource metrics
    """
    try:
        return {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent,
            'load_average': psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
        }
    except Exception as exc:
        return {'error': str(exc)}


def get_performance_metrics():
    """
    Get application performance metrics V3
    """
    try:
        one_hour_ago = timezone.now() - timedelta(hours=1)
        hourly_ingestion = TelemetryRecord.objects.filter(
            timestamp__gte=one_hour_ago
        ).count()

        return {
            'hourly_ingestion_rate_v3': hourly_ingestion,
            'avg_records_per_minute': hourly_ingestion / 60
        }
    except Exception as exc:
        return {'error': str(exc)}


def send_health_alert(health_status):
    """
    Send alert for critical health issues
    """
    try:
        from api.core.models import NotificationsCatchment
        from django.contrib.auth import get_user_model
        
        alert_message = f"🚨 ALERTA DE SISTEMA CRÍTICA (V3)\\n\\n"
        alert_message += f"Estado: {health_status['overall_status'].upper()}\\n"
        
        for service, status in health_status['services'].items():
            if status.get('status') != 'healthy':
                alert_message += f"❌ {service.upper()}: {status.get('error', 'unhealthy')}\\n"

        User = get_user_model()
        admin_users = User.objects.filter(is_staff=True)

        for admin in admin_users:
            system_point = CatchmentPoint.objects.filter(owner_user=admin).first()
            if system_point:
                NotificationsCatchment.objects.create(
                    point_catchment=system_point,
                    title="Alerta Crítica del Sistema V3",
                    message=alert_message,
                    type_notification='CRITICAL',
                    type_variable='TODOS'
                )
    except Exception as exc:
        logger.error(f"Failed to send health alert: {exc}")
