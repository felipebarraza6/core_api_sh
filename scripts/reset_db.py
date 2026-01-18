from django.db import connection
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings_dev")
django.setup()

with connection.cursor() as cursor:
    cursor.execute("DROP SCHEMA public CASCADE")
    cursor.execute("CREATE SCHEMA public")
    cursor.execute("GRANT ALL ON SCHEMA public TO public")
    print("Database public schema reset.")
