#!/usr/bin/env python3
"""
Script para arreglar el problema de transacciones en el respaldo a data_store_telemetry
"""
import os
import psycopg2
from psycopg2.extras import execute_batch

# Cargar variables del .env
def load_env():
    env_vars = {}
    with open('/app/.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
                os.environ[key] = value
    return env_vars

def test_cluster_secondary():
    """Probar conexión a data_store_telemetry"""
    try:
        env_vars = load_env()
        
        config = {
            'host': env_vars.get('CLUSTER_DB_HOST'),
            'port': int(env_vars.get('CLUSTER_DB_PORT', 25060)),
            'database': 'data_store_telemetry',  # Base secundaria
            'user': env_vars.get('CLUSTER_DB_USER_BACKUP'),
            'password': env_vars.get('CLUSTER_DB_PASSWORD_BACKUP'),
            'sslmode': env_vars.get('CLUSTER_DB_SSLMODE', 'require')
        }
        
        print(f"Conectando a data_store_telemetry...")
        print(f"Host: {config['host']}")
        print(f"Port: {config['port']}")
        print(f"User: {config['user']}")
        
        conn = psycopg2.connect(**config)
        conn.autocommit = True  # Evitar problemas de transacciones
        cursor = conn.cursor()
        
        # Test simple
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Conectado exitosamente!")
        print(f"PostgreSQL version: {version}")
        
        # Verificar permisos para crear tablas
        cursor.execute("SELECT current_database(), current_user;")
        db, user = cursor.fetchone()
        print(f"Base actual: {db}, Usuario: {user}")
        
        # Test crear tabla simple
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_permissions (
                    id SERIAL PRIMARY KEY,
                    test_data TEXT
                );
            """)
            print("✅ Permisos para crear tablas: OK")
            
            # Limpiar test
            cursor.execute("DROP TABLE IF EXISTS test_permissions;")
            
        except Exception as e:
            print(f"❌ Error permisos crear tabla: {e}")
            
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error conexión data_store_telemetry: {e}")
        return False

if __name__ == "__main__":
    test_cluster_secondary()
