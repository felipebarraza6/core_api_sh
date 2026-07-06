"""Settings API Django - PRODUCCIÓN SEGURA"""

import os
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
    "https://*.smarthydro.app",
    "https://api.smarthydro.app",
    "https://ikolu.smarthydro.app",
]
ALLOWED_HOSTS = ["*"]

# Security - Configuraciones de seguridad estrictas
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "SAMEORIGIN"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 año
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Application definition
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "jazzmin",  # Django Jazzmin - DEBE ir ANTES de django.contrib.admin
    "django.contrib.admin",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_filters",
    "django_rest_passwordreset",
    "drf_spectacular",  # OpenAPI 3.0 documentation
]

LOCAL_APPS = [
    # Core
    "api.core.apps.CoreAppConfig",
    "api.presentation.apps.PresentationConfig",
    "api.chatbot.apps.ChatbotConfig",
    "api.telemetry.apps.TelemetryConfig",
    "api.ingestion.apps.IngestionConfig",
    "api.telemetry.providers.apps.ProvidersConfig",
    "api.crm.apps.CrmConfig",
    "api.subscriptions.apps.SubscriptionsConfig",
    "api.compliance.apps.ComplianceConfig",
    "api.notifications.apps.NotificationsConfig",
    "api.documents.apps.DocumentsConfig",
    "api.infrastructure.apps.InfrastructureConfig",
    "api.support.apps.SupportConfig",
    "api.dynamic_registry.apps.DynamicRegistryConfig",
    "api.unified.apps.UnifiedConfig",
    # Propuesta VOID - Nuevos módulos
    "api.gateway.apps.GatewayConfig",       # API Gateway (rate limiting, circuit breaker, versioning)
    "api.events.apps.EventsConfig",         # Event Bus (arquitectura desacoplada)
    "api.analytics.apps.AnalyticsConfig",   # API Analytics (usage, performance, health)
    "django_celery_beat",
    "import_export",
]

# Configuración de correo para alertas - DESDE VARIABLES DE ENTORNO
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "s1042.use1.mysecurecloudhost.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 465))
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "True").lower() == "true"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "notify@smarthydro.app")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "notify@smarthydro.app")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "telemetry@smarthydro.app")

# ========================================
# FEATURE FLAGS - Control de nuevas funcionalidades
# ========================================
# Flag para usar nuevo cálculo de caudal medio diario para estándar MEDIO
USE_NEW_CAUDAL_CALCULATION_MEDIO = (
    os.environ.get("USE_NEW_CAUDAL_CALCULATION_MEDIO", "True").lower() == "true"
)

# Feature flags para módulos VOID
FEATURE_FLAGS = {
    "api_gateway": os.environ.get("FF_API_GATEWAY", "True").lower() == "true",
    "event_bus": os.environ.get("FF_EVENT_BUS", "True").lower() == "true",
    "api_analytics": os.environ.get("FF_API_ANALYTICS", "True").lower() == "true",
    "circuit_breaker": os.environ.get("FF_CIRCUIT_BREAKER", "True").lower() == "true",
    "tenant_throttling": os.environ.get("FF_TENANT_THROTTLING", "True").lower() == "true",
}

# ========================================
# DGA CONFIGURATION - Dirección General de Aguas
# ========================================
# Contraseña por defecto para software DGA
# Cada punto puede tener su propia contraseña personalizada en el modelo
DGA_DEFAULT_PASSWORD = os.environ.get("DGA_DEFAULT_PASSWORD", "")

# ========================================
# USER CONFIGURATION (DEPRECATED)
# ========================================
# DEPRECATED: No usar para nuevos usuarios
# Mantener solo para compatibilidad con datos existentes
USER_DEFAULT_PASSWORD = os.environ.get("USER_DEFAULT_PASSWORD", "pozos.2023")

# Configuración de logs para cron jobs
# CRONJOBS removed - replaced by Celery Beat


# Reordenar apps para que "Operaciones y Telemetría" aparezca primero en el menú
# LOCAL_APPS primero para que core.apps.CoreAppConfig aparezca antes que auth
INSTALLED_APPS = LOCAL_APPS + DJANGO_APPS + THIRD_PARTY_APPS

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "api.gateway.middleware.APIGatewayMiddleware",  # VOID: API Gateway lifecycle (request ID, correlation, timing)
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

# Configuración CORS más segura
CORS_ORIGIN_ALLOW_ALL = False
CORS_ORIGIN_WHITELIST = [
    "https://smarthydro.app",
    "https://www.smarthydro.app",
    "https://api.smarthydro.app",
    "https://ikolu.smarthydro.app",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:3001",
]

# FIX CORS: Permitir también patrones con regex para subdominios
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
    "x-api-version",           # VOID: Header para versionado de API
    "x-tenant-id",             # VOID: Header para multi-tenancy
    "x-correlation-id",        # VOID: Header para correlación de requests
    "x-request-id",            # VOID: Header para request tracking
]

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "api.core.exceptions.json_on_error_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # VOID: Enhanced throttling with multi-tenant support
    "DEFAULT_THROTTLE_CLASSES": [
        "api.gateway.throttling.TenantRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
    # VOID: Semantic API versioning
    "DEFAULT_VERSIONING_CLASS": "api.gateway.versioning.APIVersioning",
    "DEFAULT_VERSION": "v2",
    "ALLOWED_VERSIONS": ["v1", "v2", "v3"],
    # VOID: OpenAPI schema documentation
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# VOID: drf-spectacular configuration
SPECTACULAR_SETTINGS = {
    "TITLE": "SmartHydro Core API",
    "DESCRIPTION": "API de monitoreo hidrologico - Telemetria, alertas, reportes DGA/SMA, CRM y gestion de puntos de captacion.",
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "SERVE_AUTHENTICATION": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "TAGS": [
        {"name": "Telemetry", "description": "Operaciones de telemetria"},
        {"name": "Compliance", "description": "Cumplimiento normativo DGA/SMA"},
        {"name": "CRM", "description": "Gestion de clientes y proyectos"},
        {"name": "Analytics", "description": "Metricas y analiticas de API"},
        {"name": "Gateway", "description": "Administracion de API Gateway"},
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

# Detección de entorno Docker para configuración dinámica
IS_DOCKER = os.path.exists("/.dockerenv")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ.get("LOCAL_DB_NAME", "smarthydro_prod"),
        "USER": os.environ.get(
            "LOCAL_DB_USER", os.environ.get("POSTGRES_USER", "smarthydro_user")
        ),
        "PASSWORD": os.environ.get(
            "LOCAL_DB_PASSWORD", os.environ.get("POSTGRES_PASSWORD")
        ),
        "HOST": os.environ.get(
            "LOCAL_DB_HOST", "postgres_db_secure" if IS_DOCKER else "localhost"
        ),
        "PORT": os.environ.get("LOCAL_DB_PORT", "5432"),
        "OPTIONS": {
            "connect_timeout": 10,
            "application_name": "smarthydro_django",
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
        "CONN_MAX_AGE": 600,
        "ATOMIC_REQUESTS": True,
    }
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
        },
        "TIMEOUT": 900,
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
    os.path.join(BASE_DIR, "static"),
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
        "gateway": {
            "format": (
                "{levelname} {asctime} [gateway] {request_id} {correlation_id} "
                "{module} {message}"
            ),
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.environ.get("DJANGO_LOG_FILE", "/app/logs/django.log"),
            "maxBytes": 1024 * 1024 * 10,
            "backupCount": 5,
            "formatter": "verbose",
            "delay": True,
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "gateway_file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/app/logs/gateway.log",
            "maxBytes": 1024 * 1024 * 50,
            "backupCount": 10,
            "formatter": "gateway",
            "delay": True,
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
        "api.gateway": {
            "handlers": ["console", "gateway_file"],
            "level": "INFO",
            "propagate": False,
        },
        "api.events": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "api.analytics": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Configuración de sesiones
SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# Configuración de archivos estáticos
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ========================================
# CONFIGURACIÓN DJANGO JAZZMIN - UI MEJORADA
# ========================================
JAZZMIN_SETTINGS = {
    "site_title": "Ikolu Management",
    "site_header": "Ikolu Management",
    "site_brand": "Ikolu Management",
    "site_logo": None,
    "login_logo": None,
    "login_logo_dark": None,
    "theme": "flatly",
    "dark_mode_theme": "darkly",
    "site_icon": None,
    "topmenu_links": [
        {
            "name": "Ikolu Home",
            "url": "https://ikolu.smarthydro.app",
            "new_window": True,
            "icon": "fas fa-home",
        },
        {
            "name": "SmartHydro Web",
            "url": "https://smarthydro.cl",
            "new_window": True,
            "icon": "fas fa-globe",
        },
    ],
    "usermenu_links": [{"model": "auth.user"}],
    "show_sidebar": True,
    "navigation_expanded": True,
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "show_ui_builder": False,
    "changeform_format": "horizontal_tabs",
    "language_chooser": False,
    "copyright": "SmartHydro - Sistema de Monitoreo Hidrologico",
    "welcome_sign": "Bienvenido a SmartHydro - Panel de Control de Telemetria",
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-primary",
    "accent": "accent-info",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "flatly",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
    "actions_sticky_top": True,
}

if not DEBUG:
    X_FRAME_OPTIONS = "SAMEORIGIN"
    CORS_PREFLIGHT_MAX_AGE = 86400
    CORS_EXPOSE_HEADERS = [
        "accept",
        "accept-encoding",
        "authorization",
        "content-type",
        "dnt",
        "origin",
        "user-agent",
        "x-csrftoken",
        "x-requested-with",
        "x-request-id",
        "x-correlation-id",
        "x-api-version",
        "x-response-time-ms",
        "x-gateway-version",
        "x-rate-limit-limit",
        "x-rate-limit-remaining",
    ]

# ========================================
# CHATBOT CONFIGURATION
# ========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ========================================
# CELERY CONFIGURATION - Replaces Cronjobs
# ========================================
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ========================================
# MQTT BROKER CONFIGURATION
# ========================================
MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "mqtt_broker" if IS_DOCKER else "localhost")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", 1883))
MQTT_BROKER_USERNAME = os.environ.get("MQTT_BROKER_USERNAME", "smarthydro")
MQTT_BROKER_PASSWORD = os.environ.get("MQTT_BROKER_PASSWORD", "dev_mqtt_password")

# ========================================
# VOID: API GATEWAY CONFIGURATION
# ========================================
API_GATEWAY = {
    "VERSION": "1.0.0",
    "REQUEST_ID_HEADER": "X-Request-ID",
    "CORRELATION_ID_HEADER": "X-Correlation-ID",
    "API_VERSION_HEADER": "X-API-Version",
    "TENANT_ID_HEADER": "X-Tenant-ID",
    "DEFAULT_VERSION": "v2",
    "DEPRECATED_VERSIONS": ["v1"],
    # Circuit breaker defaults
    "CIRCUIT_BREAKER": {
        "dga_api": {
            "failure_threshold": 3,
            "recovery_timeout": 120,
            "half_open_max_calls": 2,
        },
        "sma_api": {
            "failure_threshold": 3,
            "recovery_timeout": 180,
            "half_open_max_calls": 2,
        },
        "mqtt_broker": {
            "failure_threshold": 5,
            "recovery_timeout": 30,
            "half_open_max_calls": 3,
        },
    },
    # Default tenant rate limits
    "DEFAULT_RATE_LIMITS": {
        "free": {"rpm": 30, "burst": 5},
        "basic": {"rpm": 60, "burst": 10},
        "professional": {"rpm": 300, "burst": 30},
        "enterprise": {"rpm": 1000, "burst": 100},
    },
}

# ========================================
# VOID: EVENT BUS CONFIGURATION
# ========================================
EVENT_BUS = {
    "STREAM_KEY": "smarthydro:events",
    "MAX_STREAM_LENGTH": 100000,
    "PUBLISH_TIMEOUT": 5,
    "MAX_RETRIES": 3,
    "RETRY_BACKOFF_BASE": 2,  # Exponential backoff: 2^retry seconds
    "CONSUMER_BATCH_SIZE": 10,
}

# ========================================
# VOID: ANALYTICS CONFIGURATION
# ========================================
API_ANALYTICS = {
    "HEALTH_SCORE_THRESHOLDS": {
        "latency_p95_ms": 1000,
        "error_rate_percent": 5.0,
        "availability_percent": 99.0,
    },
    "AGGREGATION_SCHEDULE": {
        "minute": "* * * * *",      # Every minute
        "hour": "0 * * * *",         # Every hour
        "day": "0 0 * * *",          # Every day
    },
    "DASHBOARD_SNAPSHOT_RANGES": ["1h", "6h", "24h", "7d", "30d"],
    "SCORE_HISTORY_RETENTION_HOURS": 24,
}
