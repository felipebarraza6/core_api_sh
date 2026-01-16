import os
from api.settings import *

# Remove jazzmin if present
if 'jazzmin' in INSTALLED_APPS:
    INSTALLED_APPS.remove('jazzmin')

# Mock static files storage if whitenoise causes issues in partial env
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Use SQLite for testing
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# Override Cache to avoid redis dependency
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}
