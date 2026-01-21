"""Settings de desarrollo para SmartHydro - USA POSTGRESQL PARA DESARROLLO REAL LOCAL"""

import os
from pathlib import Path

# Load dotenv to get database credentials
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(Path(__file__).parent.parent, ".env"))
except ImportError:
    pass

# Build paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configuración básica de desarrollo
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-for-local-testing")
DEBUG = True

ALLOWED_HOSTS = ["*"]  # Para desarrollo

# Base de datos PostgreSQL para desarrollo real local
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "smarthydro_dev"),
        "USER": os.environ.get("POSTGRES_USER", "smarthydro_dev_user"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "dev_password_123"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

# Aplicaciones mínimas pero funcionales
INSTALLED_APPS = [
    "jazzmin",  # Agregamos jazzmin para que el admin se vea bien
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # DRF
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "django_rest_passwordreset",
    "import_export",
    # Nuestras apps
    "api.core.apps.CoreAppConfig",
    "api.telemetry.apps.TelemetryConfig",
    "api.telemetry.providers.apps.ProvidersConfig",
    "api.chatbot.apps.ChatbotConfig",
    "api.crm.apps.CrmConfig",
    "api.notifications.apps.NotificationsConfig",
    "api.documents.apps.DocumentsConfig",
    "api.infrastructure.apps.InfrastructureConfig",
    "api.support.apps.SupportConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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

# Password validation (básico)
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

# Custom User Model
AUTH_USER_MODEL = "core.User"

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Configuración básica de REST Framework
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
}

# Google Chat Webhooks para modo DEV
# GOOGLE_CHAT_WEBHOOK_URL is handled via DB (SystemConfiguration) or .env
GOOGLE_CHAT_WEBHOOK_URL = os.getenv("GOOGLE_CHAT_WEBHOOK_URL", None)
GOOGLE_CHAT_WEBHOOK_DGA_URL = os.getenv("GOOGLE_CHAT_WEBHOOK_DGA_URL", None)
