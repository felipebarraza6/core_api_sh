"""
Settings para tests con SQLite en memoria.
Hereda todo de settings.py y solo sobrescribe la base de datos.
"""
from api.settings import *  # noqa: F401,F403

# Base de datos SQLite en disco para tests persistentes
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': '/tmp/smarthydro_test.db',
    }
}

# Desactivar cronjobs para tests
CRONJOBS = []

# Usar backend de email que no envía nada (solo captura en memoria)
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# No requerir conexión a Redis
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Desactivar verificaciones de migraciones consistentes
MIGRATION_MODULES = {}
