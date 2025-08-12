"""Settings API Django"""

import os
from pathlib import Path

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(Path(BASE_DIR).parent, '.env'))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', "h#v#*68y)bfb2ylvy^f-tksars9-k1#8lejxo==_3hsnu2ek!h")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'

CSRF_TRUSTED_ORIGINS = ["https://*.smarthydro.app", "https://*.127.0.0.1"]
ALLOWED_HOSTS = ["*"]

# Security
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

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
]

LOCAL_APPS = ["api.core.apps.CoreAppConfig", "django_crontab", "import_export"]

# Configuración de correo para alertas
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "s1042.use1.mysecurecloudhost.com"
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_HOST_USER = "notify@smarthydro.app"
EMAIL_HOST_PASSWORD = "notify.2025"

DEFAULT_FROM_EMAIL = "notify@smarthydro.app"
CONTACT_EMAIL = "telemetry@smarthydro.app"

CRONJOBS = [
    # tdata 60 minutos
    (
        "0 * * * *",
        "api.cronjobs.telemetry.twin.run",
        ">> "
        + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/twin_60.log")
        + " 2>&1",
    ),
    # tdata 1 minuto
    (
        "* * * * *",
        "api.cronjobs.telemetry.twin_f1.run",
        ">> "
        + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/twin_1.log")
        + " 2>&1",
    ),
    # tdata 5 minutos
    (
        "*/5 * * * *",
        "api.cronjobs.telemetry.twin_f5.run",
        ">> "
        + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/twin_5.log")
        + " 2>&1",
    ),
    # nettra 60 minutos
    (
        "0 * * * *",
        "api.cronjobs.telemetry.nettra.run",
        ">> "
        + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/nettra_60.log")
        + " 2>&1",
    ),
    # nettra 5 minutos
    (
        "*/5 * * * *",
        "api.cronjobs.telemetry.nettra_f5.run",
        ">> "
        + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/nettra_5.log")
        + " 2>&1",
    ),
    # novus 60 minutos
    (
        "0 * * * *",
        "api.cronjobs.telemetry.novus.run",
        ">> "
        + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/novus_60.log")
        + " 2>&1",
    ),
    # cola ejecución dga
    (
        "*/3 * * * *",
        "api.cronjobs.dga.cron_dga.run",
        ">> " + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/dga.log") + " 2>&1",
    ),
    # cola ejecución SMA - cada 5 minutos
    (
        "*/5 * * * *",
        "api.cronjobs.sma.cron_sma.run",
        ">> " + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/sma.log") + " 2>&1",
    ),
    # backup cluster - cada hora
    (
        "0 * * * *",
        "api.cronjobs.cluster_backup.run",
        ">> "
        + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/cluster_backup.log")
        + " 2>&1",
    ),
    # cola ejecución alertas - cada 10 minutos
    (
        "*/10 * * * *",
        "api.cronjobs.alerts.cron_alerts.run",
        ">> "
        + os.path.join(BASE_DIR, "api/cronjobs/telemetry/logs/alerts.log")
        + " 2>&1",
    ),
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

CORS_ORIGIN_ALLOW_ALL = True

CORS_ORIGIN_WHITELIST = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:3001",
]

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "drf_excel.renderers.XLSXRenderer",
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend"),
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

# Database Configuration - Configuración dual
USE_CLUSTER = os.environ.get('USE_CLUSTER', 'false').lower() == 'true'

if USE_CLUSTER:
    # Configuración para Cluster DigitalOcean (Producción)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql_psycopg2",
            "NAME": os.environ.get('CLUSTER_DB_NAME', 'telemetry_api'),
            "USER": os.environ.get('CLUSTER_DB_USER', 'api'),
            "PASSWORD": os.environ.get('CLUSTER_DB_PASSWORD'),
            "HOST": os.environ.get('CLUSTER_DB_HOST'),
            "PORT": os.environ.get('CLUSTER_DB_PORT', '25060'),
            "OPTIONS": {
                "sslmode": os.environ.get('CLUSTER_DB_SSLMODE', 'require'),
            },
        },
        # Base de datos local para cache/desarrollo
        "local": {
            "ENGINE": "django.db.backends.postgresql_psycopg2",
            "NAME": os.environ.get('LOCAL_DB_NAME', 'postgres'),
            "USER": os.environ.get('LOCAL_DB_USER', 'postgres'),
            "PASSWORD": os.environ.get('LOCAL_DB_PASSWORD', 'postgres'),
            "HOST": os.environ.get('LOCAL_DB_HOST', 'postgres'),
            "PORT": os.environ.get('LOCAL_DB_PORT', '5432'),
        }
    }
else:
    # Configuración local (Desarrollo)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql_psycopg2",
            "NAME": os.environ.get('LOCAL_DB_NAME', 'postgres'),
            "USER": os.environ.get('LOCAL_DB_USER', 'postgres'),
            "PASSWORD": os.environ.get('LOCAL_DB_PASSWORD', 'postgres'),
            "HOST": os.environ.get('LOCAL_DB_HOST', 'postgres'),
            "PORT": os.environ.get('LOCAL_DB_PORT', '5432'),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
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
STATIC_ROOT = os.path.join(BASE_DIR, "static/")
