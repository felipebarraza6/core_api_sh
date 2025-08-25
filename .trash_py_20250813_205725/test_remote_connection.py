#!/usr/bin/env python3
import os
import psycopg2

# Cargar variables del .env
def load_env():
    env_vars = {}
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
    return env_vars

env_vars = load_env()

# Configuración del cluster remoto
cluster_config = {
    'host': env_vars.get('CLUSTER_DB_HOST'),
    'port': int(env_vars.get('CLUSTER_DB_PORT', 5432)),
    'database': env_vars.get('CLUSTER_DB_NAME'),
    'user': env_vars.get('CLUSTER_DB_USER'),
    'password': env_vars.get('CLUSTER_DB_PASSWORD'),
    'sslmode': env_vars.get('CLUSTER_DB_SSLMODE', 'prefer')
}

print("Configuración del cluster:")
print(f"Host: {cluster_config['host']}")
print(f"Port: {cluster_config['port']}")
print(f"Database: {cluster_config['database']}")
print(f"User: {cluster_config['user']}")
print(f"SSL Mode: {cluster_config['sslmode']}")

try:
    print("\nIntentando conectar al cluster remoto...")
    conn = psycopg2.connect(**cluster_config)
    cursor = conn.cursor()
    
    # Test simple
    cursor.execute("SELECT version();")
    version = cursor.fetchone()[0]
    print(f"✓ Conexión exitosa!")
    print(f"PostgreSQL version: {version}")
    
    # Verificar si existe la base de datos telemetry_api
    cursor.execute("SELECT current_database();")
    current_db = cursor.fetchone()[0]
    print(f"Base de datos actual: {current_db}")
    
    # Contar tablas core_*
    cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name LIKE 'core_%';")
    core_tables = cursor.fetchone()[0]
    print(f"Tablas 'core_*' en remoto: {core_tables}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"✗ Error de conexión: {e}")
    print("Tipo de error:", type(e).__name__)
