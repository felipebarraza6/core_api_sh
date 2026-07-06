"""Settings API Django - PRODUCCIÓN SEGURA"""

import os
import sys
from pathlib import Path

# Try to load dotenv, but don't fail if not available
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(Path(__file__).parent.parent, ".env"))
except ImportError:
    # dotenv not available, continue without it
    pass

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

# Configuración de seguridad para producción
CSRF_TRUSTED_ORIGINS = [
    "https://api.smarthydro.app",
    "https://ikolu.smarthydro.app",
    "https://smarthydro.app",
    "https://*.smarthydro.app",
]
ALLOWED_HOSTS = [
    "api.smarthydro.app",
    "ikolu.smarthydro.app",
    ".smarthydro.app",  # ✅ Cloudflare: Cualquier subdominio
    "localhost",
    "127.0.0.1",
    "postgres",  # Para conexiones internas Docker
    "django",  # ✅ Docker Compose service name
    "172.25.0.2",  # ✅ Django container IP (para nginx proxy interno)
]

# Security - Configuraciones de seguridad estrictas
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True       # ✅ Solo enviar cookies por HTTPS
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True          # ✅ Solo enviar CSRF cookie por HTTPS
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
# ✅ ACTIVADO: Lee de variable de entorno (docker-compose pasa DJANGO_SECURE_SSL_REDIRECT=True)
# En tests se desactiva porque el test client WSGI no simula nginx-proxy (sin X-Forwarded-Proto)
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "False") == "True" and not TESTING
# Exención crítica: health checks internos de Docker van por HTTP directo a Gunicorn
SECURE_REDIRECT_EXEMPT = [r'^health/$']
SECURE_HSTS_SECONDS = 31536000  # 1 año
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ✅ Cloudflare: Confiar en proxy headers
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Content Security Policy (CSP) - Security Headers
# Configuración balanceada: API restrictiva + Admin funcional
CSP_DEFAULT_SRC = ("'none'",)  # Bloquear todo por defecto
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "'unsafe-eval'", "https://*.smarthydro.app", "https://smarthydro.cl", "https://static.cloudflareinsights.com", "https://cdn.jsdelivr.net", "blob:")  # Admin + subdominios + Cloudflare + CDN swagger/redoc + Workers
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net", "https://*.smarthydro.app", "https://smarthydro.cl", "https://www.smarthydro.cl")  # Estilos de subdominios + Google Fonts + CDN swagger/redoc
CSP_IMG_SRC = ("'self'", "data:", "https://cdn.jsdelivr.net", "https://*.smarthydro.app", "https://smarthydro.cl", "https://www.smarthydro.cl")  # Imágenes de subdominios + CDN swagger/redoc
CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com", "https://cdn.jsdelivr.net", "data:")  # Fuentes de Google + CDN swagger/redoc + data URIs
CSP_CONNECT_SRC = ("'self'", "https://*.smarthydro.app", "https://smarthydro.cl", "https://static.cloudflareinsights.com", "https://cdn.jsdelivr.net")  # AJAX + Cloudflare + CDN swagger/redoc
CSP_WORKER_SRC = ("'self'", "blob:")  # Permitir Web Workers
CSP_OBJECT_SRC = ("'none'",)  # Bloquear objetos (Flash, etc.)
CSP_BASE_URI = ("'self'",)  # Restringir base URI
CSP_FRAME_SRC = ("'self'", "https://*.smarthydro.app", "https://smarthydro.cl", "https://www.smarthydro.cl")  # Permitir iframes de smarthydro
CSP_FRAME_ANCESTORS = ("'none'",)  # No permitir ser embebido
CSP_FORM_ACTION = ("'self'", "https://*.smarthydro.app", "https://smarthydro.cl", "https://www.smarthydro.cl")  # Permitir formularios
CSP_MEDIA_SRC = ("'self'", "https://*.smarthydro.app", "https://smarthydro.cl", "https://www.smarthydro.cl")  # Permitir video/audio de subdominios y sitio principal
CSP_MANIFEST_SRC = ("'self'", "https://*.smarthydro.app", "https://smarthydro.cl", "https://www.smarthydro.cl")  # Permitir manifests

# Application definition
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_filters",
    "django_rest_passwordreset",
    "drf_spectacular",
]

LOCAL_APPS = ["api.core.apps.CoreAppConfig", "django_crontab", "import_export"]

# ========================================
# CONFIGURACIÓN DE CORREO - GMAIL API
# ========================================
# Backend de envío usando Gmail API en lugar de SMTP
EMAIL_BACKEND = "api.utils.gmail.GmailApiBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "soporte@smarthydro.cl")

# Ruta a credenciales de Google Service Account (JSON)
GOOGLE_SERVICE_ACCOUNT_FILE = os.path.join(
    BASE_DIR,
    os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/google_service_account_key.json")
)

# Cuenta delegada que enviará los correos (debe estar en Google Workspace)
GOOGLE_DELEGATED_USER = os.environ.get("GOOGLE_DELEGATED_USER", "soporte@smarthydro.cl")

# ========================================
# FEATURE FLAGS - Control de nuevas funcionalidades
# ========================================
# Flag para usar nuevo cálculo de caudal medio diario para estándar MEDIO
USE_NEW_CAUDAL_CALCULATION_MEDIO = os.environ.get(
    "USE_NEW_CAUDAL_CALCULATION_MEDIO", "True"
).lower() == "true"

# Modo prueba para notificaciones de SLA vencido.
# Ejemplo: '["felipebarraza@smarthydro.cl"]' para que solo llegue a Felipe.
# Dejar vacío para notificar a todos los operadores/asignados normales.
import json as _json

_sla_overdue_test_only = os.environ.get("SLA_OVERDUE_TEST_ONLY", "").strip()
if _sla_overdue_test_only:
    try:
        SLA_OVERDUE_TEST_ONLY = _json.loads(_sla_overdue_test_only)
    except _json.JSONDecodeError:
        SLA_OVERDUE_TEST_ONLY = []
else:
    SLA_OVERDUE_TEST_ONLY = []

# ========================================
# DGA CONFIGURATION - Dirección General de Aguas
# ========================================
# Contraseña por defecto para software DGA
# Cada punto puede tener su propia contraseña personalizada en el modelo
DGA_DEFAULT_PASSWORD = os.environ.get('DGA_DEFAULT_PASSWORD', '')
DGA_BASE_URL = os.environ.get('DGA_BASE_URL', 'https://apimee.mop.gob.cl/api/v1')
DGA_DEFAULT_RUT_EMPRESA = os.environ.get('DGA_DEFAULT_RUT_EMPRESA', '')

# ========================================
# SMA CONFIGURATION - Servicio de Evaluación Ambiental
# ========================================
SMA_BASE_URL = os.environ.get('SMA_BASE_URL', 'https://conexiones.sma.gob.cl/api/v1')
SMA_USERNAME = os.environ.get('SMA_USERNAME', '')
SMA_PASSWORD = os.environ.get('SMA_PASSWORD', '')

# ========================================
# GOOGLE CHAT WEBHOOKS (legacy → migrar a NotificationProvider)
# ========================================
GOOGLE_CHAT_WEBHOOK_URL = os.environ.get('GOOGLE_CHAT_WEBHOOK_URL', '')
GOOGLE_CHAT_DGA_WEBHOOK_URL = os.environ.get('GOOGLE_CHAT_DGA_WEBHOOK_URL', '')

# ========================================
# USER CONFIGURATION (DEPRECATED)
# ========================================
# DEPRECATED: No usar para nuevos usuarios
# Mantener solo para compatibilidad con datos existentes
USER_DEFAULT_PASSWORD = os.environ.get('USER_DEFAULT_PASSWORD', 'pozos.2023')

# Configuración de logs para cron jobs
CRONJOBS = [
    # LEGACY TELEMETRÍA — COMENTADOS (Fase 4: migrados al unificado)
    # Si hay que volver atrás, descomentar y ejecutar: python manage.py crontab add
    # (
    #     "0 * * * *",
    #     "api.cronjobs.telemetry.twin.run",
    #     ">> /tmp/smarthydro/twin_60.log 2>&1",
    # ),
    # (
    # UNIFICADO: novus 60 minutos
    (
        "2 * * * *",
        "api.cronjobs.telemetry.telemetry_unified.run_novus_60",
        ">> /tmp/smarthydro/unified_novus_60.log 2>&1",
    ),
    # UNIFICADO: nettra 60 minutos (paralelo a legacy para validación Fase 3)
    (
        "4 * * * *",
        "api.cronjobs.telemetry.telemetry_unified.run_nettra_60",
        ">> /tmp/smarthydro/unified_nettra_60.log 2>&1",
    ),
    # UNIFICADO: twin 60 minutos (paralelo a legacy)
    (
        "6 * * * *",
        "api.cronjobs.telemetry.telemetry_unified.run_twin_60",
        ">> /tmp/smarthydro/unified_twin_60.log 2>&1",
    ),
    # UNIFICADO: twin 5 minutos (paralelo a legacy, offset 1 min)
    (
        "1-59/5 * * * *",
        "api.cronjobs.telemetry.telemetry_unified.run_twin_5",
        ">> /tmp/smarthydro/unified_twin_5.log 2>&1",
    ),
    # UNIFICADO: twin 10 minutos (paralelo a legacy, offset 1 min)
    (
        "1-59/10 * * * *",
        "api.cronjobs.telemetry.telemetry_unified.run_twin_10",
        ">> /tmp/smarthydro/unified_twin_10.log 2>&1",
    ),
    # UNIFICADO: twin 1 minuto (corre cada 1 min, alineado con frecuency=1)
    (
        "* * * * *",
        "api.cronjobs.telemetry.telemetry_unified.run_twin_1",
        ">> /tmp/smarthydro/unified_twin_1.log 2>&1",
    ),
    # cola ejecución dga
    (
        "*/3 * * * *",
        "api.cronjobs.dga.cron_dga.run",
        ">> /tmp/smarthydro/dga.log 2>&1",
    ),
    # cola ejecución sma
    (
        "*/5 * * * *",
        "api.cronjobs.sma.cron_sma.run",
        ">> /tmp/smarthydro/sma.log 2>&1",
    ),
    # cluster_backup habilitado
    (
        "0 * * * *",
        "api.cronjobs.space_backup.run",
        ">> /tmp/smarthydro/space_backup.log 2>&1",
    ),
    # alertas legacy (monolito NotificationsCatchment) — APAGADO
    # Las alertas umbral ahora se evalúan vía alert_engine.py (AlertRule).
    # Solo quedan activos tickets de soporte (SUPPORT) en el modelo legacy.
    # (
    #     "*/10 * * * *",
    #     "api.cronjobs.alerts.cron_alerts.run",
    #     ">> /tmp/smarthydro/alerts.log 2>&1",
    # ),
    # motor de alertas nuevo (AlertRule / AlertTrigger)
    (
        "* * * * *",
        "api.cronjobs.alerts.alert_engine.run",
        ">> /tmp/smarthydro/alert_engine.log 2>&1",
    ),
    # dispatcher de alertas nuevo (envía notificaciones pendientes)
    (
        "* * * * *",
        "api.cronjobs.alerts.alert_dispatcher.run_dispatcher",
        ">> /tmp/smarthydro/alert_dispatcher.log 2>&1",
    ),
    # boletín diario - 10:00 PM Chile (01:00 UTC)
    (
        "0 1 * * *",
        "api.cronjobs.reports.daily_bulletin.run",
        ">> /tmp/smarthydro/daily_bulletin.log 2>&1",
    ),
    # reporte diario chat - 09:00 AM Chile (12:00 UTC)
    (
        "0 12 * * *",
        "api.cronjobs.reports.daily_chat_report.run",
        ">> /tmp/smarthydro/daily_chat_report.log 2>&1",
    ),
    # reporte diario tickets activos - 10:00 AM Chile (13:00 UTC)
    (
        "0 13 * * *",
        "api.cronjobs.reports.daily_active_tickets.run",
        ">> /tmp/smarthydro/daily_active_tickets.log 2>&1",
    ),
    # reporte horario DGA MAYOR - cada hora a los :05 (reporta hora anterior)
    (
        "5 * * * *",
        "api.cronjobs.reports.dga_mayor_hourly.run",
        ">> /tmp/smarthydro/dga_mayor_hourly.log 2>&1",
    ),
    # notificación de tickets con SLA vencido
    (
        "0 * * * *",
        "api.core.management.commands.notify_sla_overdue",
        ">> /tmp/smarthydro/notify_sla_overdue.log 2>&1",
    ),
    # limpieza de tickets internos inactivos - 02:00 UTC
    (
        "0 2 * * *",
        "api.core.management.commands.cleanup_stale_internal_tickets",
        ">> /tmp/smarthydro/cleanup_stale_internal_tickets.log 2>&1",
    ),
]



# Reordenar apps para que "Operaciones y Telemetría" aparezca primero en el menú
# LOCAL_APPS primero para que core.apps.CoreAppConfig aparezca antes que auth
INSTALLED_APPS = LOCAL_APPS + DJANGO_APPS + THIRD_PARTY_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",  # Content Security Policy
    "django.middleware.gzip.GZipMiddleware",  # ✅ RENDIMIENTO: Compresión de respuestas (debe ir temprano)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # Mover antes de CommonMiddleware
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Configuración CORS más segura
CORS_ORIGIN_ALLOW_ALL = False  # Cambiar a False en producción
CORS_ORIGIN_WHITELIST = [
    "https://smarthydro.app",
    "https://www.smarthydro.app",
    "https://api.smarthydro.app",
    "https://ikolu.smarthydro.app",
    "http://localhost:3000",  # Solo para desarrollo
    "http://localhost:8000",  # Solo para desarrollo
    "http://localhost:3001",  # Local UI development
]

# ✅ FIX CORS: Permitir también patrones con regex para subdominios
CORS_ORIGIN_REGEX_WHITELIST = [
    r"^https://.*\.smarthydro\.app$",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "referer",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
]

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "api.core.exceptions.json_on_error_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework.authentication.TokenAuthentication",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SmartHydro API",
    "DESCRIPTION": "API de monitoreo hidrológico — Telemetría, alertas, reportes DGA/SMA y gestión de puntos de captación.",
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "SERVE_AUTHENTICATION": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
}

ROOT_URLCONF = "api.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "api.wsgi.application"

# ========================================
# CONFIGURACIÓN DE BASE DE DATOS - PRODUCCIÓN SEGURA
# ========================================
# IMPORTANTE: En producción, Django SIEMPRE usa la base LOCAL del VPS
# El cluster solo se usa para sincronización y respaldo automático

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ.get("LOCAL_DB_NAME", "smarthydro_prod"),
        "USER": os.environ.get("LOCAL_DB_USER", "smarthydro_user"),
        "PASSWORD": os.environ.get("LOCAL_DB_PASSWORD"),
        "HOST": os.environ.get("LOCAL_DB_HOST", "postgres_db_secure"),
        "PORT": os.environ.get("LOCAL_DB_PORT", "5432"),
        "OPTIONS": {
            "connect_timeout": 10,
            "application_name": "smarthydro_django",
            "keepalives": 1,  # Habilitar keepalive para reutilizar conexiones
            "keepalives_idle": 30,  # Segundos antes de enviar keepalive
            "keepalives_interval": 10,  # Intervalo entre keepalives
            "keepalives_count": 5,  # Número de keepalives antes de cerrar
        },
        "CONN_MAX_AGE": 600,  # 10 minutos - reutilizar conexiones
        "ATOMIC_REQUESTS": True,
    }
}

# Redis: construir URL dinámicamente para soportar both con y sin password
_redis_password = os.environ.get("REDIS_PASSWORD", "")
_redis_url = (
    f"redis://:{_redis_password}@redis_secure:6379/1"
    if _redis_password
    else "redis://redis_secure:6379/1"
)

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": _redis_url,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,  # Fallback gracefully if Redis is down
        },
        "TIMEOUT": 900,  # 15 minutes
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": ("django.contrib.auth.password_validation." "MinimumLengthValidator"),
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": ("django.contrib.auth.password_validation." "CommonPasswordValidator"),
    },
    {
        "NAME": ("django.contrib.auth.password_validation." "NumericPasswordValidator"),
    },
]

# Internationalization
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Santiago"

USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
AUTH_USER_MODEL = "core.User"
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media/")
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Directorios adicionales para archivos estáticos
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),  # Archivos estáticos del proyecto
]

# Configuración de logging para producción
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": (
                "{levelname} {asctime} {module} {process:d} {thread:d} " "{message}"
            ),
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/app/logs/django.log",
            "maxBytes": 1024 * 1024 * 10,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
            "delay": True,
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
        },
        "api": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "cronjobs": {
            "handlers": [],  # Los handlers están en logging_config.py
            "propagate": False,
        },
    },
}

# Configuración de sesiones
SESSION_COOKIE_AGE = 3600  # 1 hora
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# Configuración de archivos estáticos
# Usar CompressedStaticFilesStorage en lugar de CompressedManifestStaticFilesStorage
# para evitar errores con archivos .map faltantes
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

# ========================================
# CONFIGURACIÓN ADMIN - UI ESTÁNDAR DJANGO
# ========================================
# Se usa el admin por defecto de Django con CSS personalizado
# en admin_improvements.css para un aspecto profesional y estable.
# Jazzmin fue removido por inestabilidad en tabs y layout.
# Configuraciones CORS adicionales para producción
CORS_PREFLIGHT_MAX_AGE = 86400
CORS_EXPOSE_HEADERS = [
        'accept',
        'accept-encoding',
        'authorization',
        'content-type',
        'dnt',
        'origin',
        'user-agent',
        'x-csrftoken',
        'x-requested-with',
    ]

# ========================================
# CHATBOT CONFIGURATION
# ========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

