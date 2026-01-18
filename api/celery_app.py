"""
Celery Configuration for SmartHydro Telemetry Processing
Replaces traditional cronjobs with scalable task queue
"""

import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')

# Create the Celery app instance
app = Celery('smarthydro')

# Load task modules from all registered Django app configs
app.autodiscover_tasks()

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes
app.config_from_object('django.conf:settings', namespace='CELERY')

# Configure Celery settings
app.conf.update(
    # Task routing
    task_routes={
        'api.core.tasks.telemetry.*': {'queue': 'telemetry'},
        'api.core.tasks.dga.*': {'queue': 'dga'},
        'api.core.tasks.alerts.*': {'queue': 'alerts'},
        'api.core.tasks.reports.*': {'queue': 'reports'},
    },

    # Task execution settings
    task_acks_late=True,  # Tasks acknowledged after completion
    worker_prefetch_multiplier=1,  # Fair queuing
    task_reject_on_worker_lost=True,  # Re-queue on worker crash

    # Result backend (for tracking task results)
    result_backend='redis://redis:6379/2',
    result_expires=3600,  # 1 hour

    # Timezone
    timezone='America/Santiago',
    enable_utc=True,

    # Force PersistentScheduler instead of DatabaseScheduler
    beat_scheduler='celery.beat:PersistentScheduler',

    # Beat schedule (replaces cronjobs)
    # 🔥 ARQUITECTURA UNIFICADA - Reemplaza twin.py, twin_f1.py, twin_f5.py, twin_f10.py
    beat_schedule={
        # ========================================================================
        # TELEMETRY COLLECTION - UNIFIED TASKS
        # ========================================================================
        # Antes: 4 archivos duplicados (twin.py, twin_f1.py, twin_f5.py, twin_f10.py)
        # Ahora: 1 solo task con diferentes frecuencias

        'collect-telemetry-1min': {
            'task': 'api.core.tasks.telemetry.collect_telemetry',
            'schedule': 60.0,  # Every 60 seconds (1 minute)
            'args': ('1',),
            'options': {'queue': 'telemetry', 'priority': 9}  # Alta prioridad
        },
        'collect-telemetry-5min': {
            'task': 'api.core.tasks.telemetry.collect_telemetry',
            'schedule': 300.0,  # Every 5 minutes
            'args': ('5',),
            'options': {'queue': 'telemetry', 'priority': 7}
        },
        'collect-telemetry-10min': {
            'task': 'api.core.tasks.telemetry.collect_telemetry',
            'schedule': 600.0,  # Every 10 minutes
            'args': ('10',),
            'options': {'queue': 'telemetry', 'priority': 5}
        },
        'collect-telemetry-60min': {
            'task': 'api.core.tasks.telemetry.collect_telemetry',
            'schedule': crontab(minute=0),  # Every hour at :00
            'args': ('60',),
            'options': {'queue': 'telemetry', 'priority': 3}
        },

        # DGA processing
        'process-dga-queue': {
            'task': 'api.core.tasks.dga.process_dga_queue',
            'schedule': crontab(minute='*/3'),  # Every 3 minutes
            'options': {'queue': 'dga'}
        },

        # Alerts processing
        'process-alerts': {
            'task': 'api.core.tasks.alerts.process_alerts',
            'schedule': crontab(minute='*/10'),  # Every 10 minutes
            'options': {'queue': 'alerts'}
        },

        # Daily reports
        'daily-bulletin': {
            'task': 'api.core.tasks.reports.generate_daily_bulletin',
            'schedule': crontab(hour=1, minute=0),  # 01:00 CLT (04:00 UTC)
            'options': {'queue': 'reports'}
        },
        'daily-chat-report': {
            'task': 'api.core.tasks.reports.generate_daily_chat_report',
            'schedule': crontab(hour=12, minute=0),  # 12:00 UTC (09:00 CLT)
            'options': {'queue': 'reports'}
        },
        'dga-major-hourly': {
            'task': 'api.core.tasks.reports.generate_dga_major_hourly',
            'schedule': crontab(minute=5),  # Every hour at :05
            'options': {'queue': 'reports'}
        },

        # Maintenance tasks
        'cleanup-old-data': {
            'task': 'api.core.tasks.maintenance.cleanup_old_telemetry',
            'schedule': crontab(hour=2, minute=0),  # Daily at 02:00
            'options': {'queue': 'maintenance'}
        },
        'optimize-database': {
            'task': 'api.core.tasks.maintenance.optimize_database_weekly',
            'schedule': crontab(hour=3, minute=0, day_of_week=0),  # Sunday 03:00
            'options': {'queue': 'maintenance'}
        },

        # Health monitoring
        'health-check': {
            'task': 'api.core.tasks.monitoring.perform_health_check',
            'schedule': 300.0,  # Every 5 minutes
            'options': {'queue': 'monitoring'}
        },
    },

    # Monitoring and metrics
    worker_send_task_events=True,
    task_send_sent_event=True,
    worker_disable_rate_limits=False,

    # Error handling
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    task_retry_backoff=True,
)


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup"""
    print(f'Request: {self.request!r}')