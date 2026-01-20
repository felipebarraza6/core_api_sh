"""
Celery Tasks for Alert Processing (V3)
Replaces legacy InteractionDetail logic with dynamic TelemetryRecord
"""

import logging
import time
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from api.telemetry.models import TelemetryRecord, CatchmentPoint
from api.notifications.models import Notification

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def process_alerts(self):
    """
    Process all active alerts for V3 telemetry
    """
    start_time = time.time()
    try:
        logger.info("Starting alert processing V3")
        active_alerts = Notification.objects.filter(
            is_active=True,
            is_read=False
        ).select_related('point_catchment')

        if not active_alerts.exists():
            return {'status': 'completed', 'alerts_processed': 0}

        processed = 0
        notifications_created = 0

        for alert in active_alerts:
            try:
                with transaction.atomic():
                    created = process_single_alert(alert)
                    if created:
                        notifications_created += 1
                    processed += 1
            except Exception as exc:
                logger.error(f"Failed to process alert {alert.id}: {exc}")

        return {
            'status': 'completed',
            'alerts_processed': processed,
            'notifications_created': notifications_created,
            'execution_time': time.time() - start_time
        }
    except Exception as exc:
        logger.error(f"Alert processing failed: {exc}")
        self.retry(countdown=60, exc=exc)


def process_single_alert(alert):
    """
    Evaluate alert and notify if triggered
    """
    try:
        point = alert.point_catchment
        now = timezone.now()
        if (alert.start_date and now < alert.start_date) or (alert.end_date and now > alert.end_date):
            return False

        time_window = timedelta(hours=1)
        recent_data = get_recent_telemetry_for_alert(point, time_window)
        if not recent_data:
            return False

        if evaluate_alert_conditions(alert, recent_data):
            create_alert_notification(alert, recent_data)
            return True
        return False
    except Exception as exc:
        logger.error(f"Error processing alert {alert.id}: {exc}")
        return False


def get_recent_telemetry_for_alert(point, time_window):
    """
    Get latest valid V3 record
    """
    try:
        cutoff_time = timezone.now() - time_window
        latest_record = TelemetryRecord.objects.filter(
            point=point,
            timestamp__gte=cutoff_time,
            is_error=False
        ).order_by('-timestamp').first()

        if not latest_record:
            return None

        data = latest_record.data
        return {
            'record': latest_record,
            'flow': data.get('flow', data.get('caudal', 0)),
            'level': data.get('nivel', 0),
            'total': data.get('total', 0),
            'timestamp': latest_record.timestamp
        }
    except Exception as exc:
        logger.error(f"Error getting telemetry for alert: {exc}")
        return None


def evaluate_alert_conditions(alert, telemetry_data):
    """
    Evaluate V3 alert logic
    """
    try:
        value = get_alert_variable_value(alert, telemetry_data)
        if value is None:
            return False

        threshold = alert.threshold_value
        alert_type = alert.alert_type

        if alert_type == 'MAX':
            return value > threshold
        elif alert_type == 'MIN':
            return value < threshold
        elif alert_type == 'EQUALS':
            return abs(value - threshold) < 0.01
        elif alert_type == 'RANGE':
            max_threshold = alert.threshold_max_value
            return threshold <= value <= max_threshold if max_threshold is not None else False
        return False
    except Exception as exc:
        return False


def get_alert_variable_value(alert, telemetry_data):
    """
    Extract value from V3 data map
    """
    variable_map = {
        'NIVEL': telemetry_data.get('level'),
        'CAUDAL': telemetry_data.get('flow'),
        'TOTALIZADO': telemetry_data.get('total'),
        'TODOS': telemetry_data.get('flow')
    }
    return variable_map.get(alert.type_variable)


def create_alert_notification(alert, telemetry_data):
    """
    Create response notification
    """
    try:
        from api.notifications.models import NotificationResponse
        message = format_alert_message(alert, telemetry_data)
        NotificationResponse.objects.create(
            notification=alert,
            user=alert.point_catchment.owner_user,
            response=message
        )
        if not alert.is_periodic:
            alert.is_read = True
            alert.is_resolved = True
            alert.save(update_fields=['is_read', 'is_resolved'])
    except Exception as exc:
        logger.error(f"Error creating alert notification: {exc}")


def format_alert_message(alert, telemetry_data):
    """
    Format V3 alert message
    """
    record = telemetry_data['record']
    value = get_alert_variable_value(alert, telemetry_data)
    message = f"🚨 ALERTA: {alert.title}\n\n"
    message += f"Punto: {alert.point_catchment.title}\n"
    message += f"Valor: {value}\n"
    message += f"Timestamp: {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
    return message
