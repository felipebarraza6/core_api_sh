#!/usr/bin/env python3
import os
import sys
import psycopg2
from psycopg2.extras import execute_batch
import django
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

# Cargar variables del .env
def load_env_simple():
    with open('/app/.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

load_env_simple()

# Configuraciones
LOCAL_DB = {
    "host": os.environ.get("LOCAL_DB_HOST", "postgres_secure"),
    "port": os.environ.get("LOCAL_DB_PORT", "5432"),
    "user": os.environ.get("LOCAL_DB_USER", "smarthydro_user"),
    "password": os.environ.get("LOCAL_DB_PASSWORD", ""),
    "database": os.environ.get("LOCAL_DB_NAME", "smarthydro_prod"),
}

CLUSTER_DB = {
    "host": os.environ.get("CLUSTER_DB_HOST"),
    "port": os.environ.get("CLUSTER_DB_PORT", "25060"),
    "user": os.environ.get("CLUSTER_DB_USER"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD"),
    "database": "telemetry_api",
    "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
}

CLUSTER_DB_BACKUP = {
    "host": os.environ.get("CLUSTER_DB_HOST"),
    "port": os.environ.get("CLUSTER_DB_PORT", "25060"),
    "user": os.environ.get("CLUSTER_DB_USER_BACKUP"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD_BACKUP"),
    "database": "data_store_telemetry",
    "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
}

def test_connections():
    print("=== TESTING CONNECTIONS ===")
    
    # Test local
    try:
        print(f"LOCAL: {LOCAL_DB['host']}:{LOCAL_DB['port']}")
        conn = psycopg2.connect(**LOCAL_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        count = cursor.fetchone()[0]
        print(f"✅ LOCAL: {count} registros InteractionDetail")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ LOCAL ERROR: {e}")
    
    # Test cluster primary
    try:
        print(f"PRIMARY: {CLUSTER_DB['host']}:{CLUSTER_DB['port']} -> {CLUSTER_DB['database']}")
        conn = psycopg2.connect(**CLUSTER_DB)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        count = cursor.fetchone()[0]
        print(f"✅ PRIMARY: {count} registros InteractionDetail")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ PRIMARY ERROR: {e}")
    
    # Test cluster secondary
    try:
        print(f"SECONDARY: {CLUSTER_DB_BACKUP['host']}:{CLUSTER_DB_BACKUP['port']} -> {CLUSTER_DB_BACKUP['database']}")
        conn = psycopg2.connect(**CLUSTER_DB_BACKUP)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if InteractionDetail exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'core_interactiondetail' AND table_schema = 'public'
            )
        """)
        exists = cursor.fetchone()[0]
        
        if exists:
            cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
            count = cursor.fetchone()[0]
            print(f"✅ SECONDARY: {count} registros InteractionDetail")
        else:
            print("✅ SECONDARY: Conectado (tabla InteractionDetail no existe aún)")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ SECONDARY ERROR: {e}")

if __name__ == "__main__":
    test_connections()
