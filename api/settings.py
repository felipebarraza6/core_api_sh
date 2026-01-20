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
    "jazzmin",  # ✅ Django Jazzmin - DEBE ir ANTES de django.contrib.admin
    "django.contrib.admin",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_filters",
    "django_rest_passwordreset",
]

LOCAL_APPS = [
    "api.core.apps.CoreAppConfig",
    "api.chatbot.apps.ChatbotConfig",
    "api.reports.apps.ReportsConfig",
    "api.telemetry.apps.TelemetryConfig",
    "api.telemetry.providers.apps.ProvidersConfig",  # Sistema dinámico de proveedores
    "api.crm.apps.CrmConfig",  # 🆕 Gestión de Clientes y Proyectos
    "api.notifications.apps.NotificationsConfig",  # 🆕 Sistema de Notificaciones
    "api.documents.apps.DocumentsConfig",  # 🆕 Gestión Documental
    "api.infrastructure.apps.InfrastructureConfig",  # 🆕 Infraestructura IoT
    "api.support.apps.SupportConfig",
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
    "django_prometheus.middleware.PrometheusBeforeMiddleware",  # ✅ Prometheus: Before all
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # ✅ RENDIMIENTO: Compresión de respuestas (debe ir temprano)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # Mover antes de CommonMiddleware
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",  # ✅ Prometheus: After all
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
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
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
            "keepalives": 1,  # Habilitar keepalive para reutilizar conexiones
            "keepalives_idle": 30,  # Segundos antes de enviar keepalive
            "keepalives_interval": 10,  # Intervalo entre keepalives
            "keepalives_count": 5,  # Número de keepalives antes de cerrar
        },
        "CONN_MAX_AGE": 600,  # 10 minutos - reutilizar conexiones
        "ATOMIC_REQUESTS": True,
    }
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
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
            "filename": os.environ.get("DJANGO_LOG_FILE", "/app/logs/django.log"),
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
        "handlers": ["console", "file"],
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
    },
}

# Configuración de sesiones
SESSION_COOKIE_AGE = 3600  # 1 hora
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# Configuración de archivos estáticos
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ========================================
# CONFIGURACIÓN DJANGO JAZZMIN - UI MEJORADA
# ========================================
JAZZMIN_SETTINGS = {
    # Título del sitio
    # Título del sitio
    "site_title": "Ikolu Management",
    "site_header": "Ikolu Management",
    "site_brand": "Ikolu Management",
    # Logo de Ikolu - Texto en vez de imagen
    "site_logo": None,
    "login_logo": None,
    "login_logo_dark": None,
    # Tema y colores personalizados - Mejor contraste
    "theme": "flatly",  # Tema moderno y limpio con buen contraste
    "dark_mode_theme": "darkly",  # Tema oscuro alternativo
    # Iconos
    "site_icon": None,  # Puedes agregar un favicon aquí
    # Menú personalizado con grupos organizados
    "topmenu_links": [
        # Enlaces externos
        {
            "name": "Panel de control",
            "url": "/admin/",
            "icon": "fas fa-home",
            "permissions": ["auth.view_user"],
        },
        {
            "name": "Dashboard",
            "url": "/admin/dashboard/",
            "icon": "fas fa-chart-line",
            "permissions": ["auth.view_user"],
        },
        {
            "name": "Monitoreo",
            "url": "/admin/telemetry-monitoring/",
            "icon": "fas fa-tachometer-alt",
            "permissions": ["auth.view_user"],
        },
        {
            "name": "SmartHydro Web",
            "url": "https://smarthydro.cl",
            "new_window": True,
            "icon": "fas fa-globe",
        },
    ],
    # Menú lateral personalizado con grupos (Jazzmin 3.x)
    "usermenu_links": [{"model": "auth.user"}],
    # Configuración del menú lateral
    "show_sidebar": True,
    "navigation_expanded": True,
    # Orden y agrupación del menú - Organizado por flujo de trabajo
    "order_with_respect_to": [
        # OPERACIÓN DE TELEMETRÍA (Prioridad 1 - Lo más importante)
        "core.TelemetryRecord",  # Registros de telemetría
        "core.CatchmentPoint",  # Puntos de captación
        # INGESTA DE DATOS (Prioridad 2 - Entrada de datos)
        "core.TelemetryScheme",  # ✅ Esquemas de Telemetría (NUEVO)
        "core.Variable",  # Variables capturadas
        # PROCESAMIENTO (Prioridad 3 - Transformación de datos)
        "core.ProfileDataConfigCatchment",  # Configuración de procesamiento
        # CONFIGURACIÓN (Prioridad 4 - Estructura)
        "core.ProjectCatchments",  # Proyectos
        "core.Client",  # Clientes
        # PREPARACIÓN Y ENVÍO (Prioridad 5 - Preparación para DGA)
        "core.DgaDataConfigCatchment",  # Configuración DGA
        "core.ProfileIkoluCatchment",  # Perfiles Ikolu
        # ALERTAS Y NOTIFICACIONES (Prioridad 6)
        "core.NotificationsCatchment",
        "core.ResponseNotificationsCatchment",
        # DOCUMENTOS (Prioridad 7)
        "core.FileCatchment",
        "core.TypeFileCatchment",
        # ADMINISTRACIÓN (Prioridad 8)
        "core.User",
        "auth.Group",
        "core.RegisterPersons",
    ],
    # Personalización de modelos
    "custom_links": {
        "core.CatchmentPoint": [
            {
                "name": "Ver Dashboard",
                "url": "/admin/dashboard/",
                "icon": "fas fa-chart-line",
            }
        ],
        "core.TelemetryRecord": [
            {
                "name": "Ver Dashboard",
                "url": "/admin/dashboard/",
                "icon": "fas fa-chart-line",
            }
        ],
    },
    # Iconos personalizados para modelos - Organizados por flujo
    "icons": {
        # Autenticación
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        # Operación de Telemetría
        "core.TelemetryRecord": "fas fa-database",  # Registros
        "core.CatchmentPoint": "fas fa-map-marker-alt",  # Puntos
        "core.ProjectCatchments": "fas fa-project-diagram",  # Proyectos
        "core.Client": "fas fa-building",  # Clientes
        # Ingesta
        "core.TelemetryScheme": "fas fa-layer-group",  # ✅ Esquemas
        "core.Variable": "fas fa-signal",  # Variables capturadas
        # Procesamiento
        "core.ProfileDataConfigCatchment": "fas fa-cogs",  # Config procesamiento
        # Preparación y Envío
        "core.DgaDataConfigCatchment": "fas fa-paper-plane",  # Envío DGA
        "core.ProfileIkoluCatchment": "fas fa-user-cog",  # Perfiles
        # Alertas
        "core.NotificationsCatchment": "fas fa-bell",
        "core.ResponseNotificationsCatchment": "fas fa-reply",
        # Documentos
        "core.FileCatchment": "fas fa-file-alt",
        "core.TypeFileCatchment": "fas fa-folder-open",
        # Administración
        "core.User": "fas fa-user-tie",
        "core.RegisterPersons": "fas fa-address-book",
    },
    # Configuración de UI
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    # Relaciones con modelos relacionados
    "related_modal_active": True,
    # Personalización de la barra superior
    "custom_css": "admin/css/admin_improvements.css",  # CSS personalizado para mejoras generales
    "custom_js": None,  # Puedes agregar JavaScript personalizado aquí
    # Mostrar UI personalizada
    "show_ui_builder": False,  # Desactivar el UI builder por defecto
    # Cambiar el logo en la página de login
    "changeform_format": "horizontal_tabs",  # horizontal_tabs, collapsible, carousel, single
    # Configuración de campos
    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs",
    },
    # Idioma
    "language_chooser": False,  # Ya está en español
    # Copyright
    "copyright": "SmartHydro - Sistema de Monitoreo Hidrológico",
    # Mostrar sidebar
    "show_sidebar": True,
    # Navegación
    "navigation_expanded": True,
    # Filtros
    "filter_horizontal": True,
    # Búsqueda
    # Búsqueda global desactivada para evitar problemas de layout
    # "search_model": ["core.CatchmentPoint", "core.TelemetryRecord", "core.Client"],
    # Personalización de la página de inicio
    "welcome_sign": "Bienvenido a SmartHydro - Panel de Control de Telemetría",
    # Colores personalizados (opcional)
    "usermenu_links": [
        {"name": "Dashboard", "url": "/admin/dashboard/", "icon": "fas fa-chart-line"},
        {
            "name": "Monitoreo",
            "url": "/admin/telemetry-monitoring/",
            "icon": "fas fa-tachometer-alt",
        },
    ],
}

# Configuración del tema oscuro (opcional) - Mejorado con mejor contraste
JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-primary",
    "accent": "accent-info",  # Cambiado a info para mejor contraste
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,  # Mejor indentación para jerarquía
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

# Configuración temporal para debug de CORS
if not DEBUG:
    # Permitir X-Frame-Options para CORS
    X_FRAME_OPTIONS = "SAMEORIGIN"  # Cambiar de DENY a SAMEORIGIN

    # Configuraciones CORS adicionales para producción
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
    ]

# ========================================
# CHATBOT CONFIGURATION
# ========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ========================================
# CELERY CONFIGURATION - Replaces Cronjobs
# ========================================
# Using Redis as message broker and result backend
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Celery Beat settings (replaces traditional cronjobs)
# Use DatabaseScheduler to manage tasks from Django Admin (optional override)
# Default Beat schedule is defined in api/celery_app.py
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
