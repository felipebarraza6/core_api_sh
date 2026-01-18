from django.db import connection
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings_dev")
django.setup()

with connection.cursor() as cursor:
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'core_%'")
    tables = [row[0] for row in cursor.fetchall()]
    
    # Also drop django_migrations entries for core to be super clean
    cursor.execute("DELETE FROM django_migrations WHERE app = 'core'")
    
    for table in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            print(f"Dropped {table}")
        except Exception as e:
            print(f"Failed to drop {table}: {e}")
