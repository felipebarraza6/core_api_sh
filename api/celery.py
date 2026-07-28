"""
Configuración de Celery para SmartHydro.

Celery se introduce de forma progresiva: por ahora solo expone una tarea de
prueba (ping) y un health check. No reemplaza django-crontab todavía.
"""

import os

from celery import Celery


# ============================================================
# Construcción de la URL de Redis usando las mismas variables
# de entorno que usa el resto de la aplicación.
# ============================================================
REDIS_HOST = os.environ.get("REDIS_HOST", "redis_secure")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
REDIS_DB_BROKER = os.environ.get("REDIS_DB_BROKER", "0")
REDIS_DB_BACKEND = os.environ.get("REDIS_DB_BACKEND", "1")

if REDIS_PASSWORD:
    broker_url = (
        f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB_BROKER}"
    )
    backend_url = (
        f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB_BACKEND}"
    )
else:
    broker_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB_BROKER}"
    backend_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB_BACKEND}"

# ============================================================
# App Celery
# ============================================================
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")

app = Celery("smarthydro")

app.conf.update(
    broker_url=broker_url,
    result_backend=backend_url,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Santiago",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
    # Nombres de cola por defecto
    task_default_queue="smarthydro",
    # Schedule de shadow mode: validación continua conservadora.
    # No reemplaza crontab legacy; corre en paralelo y compara salidas.
    beat_schedule={
        "void-shadow-sample": {
            "task": "void.tasks.void_shadow_sample",
            "schedule": 300.0,  # cada 5 minutos
            "kwargs": {"max_devices": 3, "window_minutes": 70},
            "options": {"queue": "smarthydro"},
        },
        "void-check-subscriptions": {
            "task": "void.tasks.void_check_subscriptions",
            "schedule": 86400.0,  # cada 24 horas
            "options": {"queue": "smarthydro"},
        },
        "void-process-compliance-queue": {
            "task": "void.tasks.void_process_compliance_queue",
            "schedule": 300.0,  # cada 5 minutos
            "kwargs": {"max_submissions": 30},
            "options": {"queue": "smarthydro"},
        },
    },
)

# Cargar configuración desde settings.py (objeto celery_config si existe)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover de tareas en apps Django instaladas
app.autodiscover_tasks()
