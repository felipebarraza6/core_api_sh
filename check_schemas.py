#!/usr/bin/env python3
"""Check actual schemas in cluster vs local"""
import psycopg2
import os
import sys

# Read .env
env = {}
with open('/app/.env') as f:
    for line in f:
        if '=' in line and not line.strip().startswith('#'):
            key, val = line.strip().split('=', 1)
            env[key] = val

print("=" * 60)
print("VERIFICANDO ESQUEMAS")
print("=" * 60)
sys.stdout.flush()

# Connect to cluster
print("\n📡 Conectando al cluster...")
sys.stdout.flush()

remote_conn = psycopg2.connect(
    host=env['CLUSTER_DB_HOST'],
    port=int(env['CLUSTER_DB_PORT']),
    user=env['CLUSTER_DB_USER'],
    password=env['CLUSTER_DB_PASSWORD'],
    database='data_store_telemetry',
    sslmode='require'
)

remote_cursor = remote_conn.cursor()

# Get schema for each table
tables = [
    'core_client',
    'core_projectcatchments',
    'core_catchmentpoint',
    'core_schemescatchment',
    'core_variable',
    'core_dgadataconfigcatchment',
    'core_profiledataconfigcatchment'
]

for table in tables:
    print(f"\n=== {table.upper()} ===")
    sys.stdout.flush()

    remote_cursor.execute(f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = '{table}'
        ORDER BY ordinal_position
    """)

    columns = remote_cursor.fetchall()
    if columns:
        for col_name, col_type in columns:
            print(f"  {col_name}: {col_type}")
    else:
        print(f"  ⚠️  Table not found")

    # Get count
    try:
        remote_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = remote_cursor.fetchone()[0]
        print(f"  Total: {count:,} registros")
    except Exception as e:
        print(f"  Error: {e}")

    sys.stdout.flush()

# Connect to local
print("\n📡 Conectando a local...")
sys.stdout.flush()

local_conn = psycopg2.connect(
    host='postgres',
    port=5432,
    user='smarthydro_user',
    password='smarthydro_password_2025',
    database='smarthydro_prod'
)

local_cursor = local_conn.cursor()

print("\n=== CONTEOS LOCALES ===")
for table in tables:
    try:
        local_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = local_cursor.fetchone()[0]
        print(f"  {table}: {count:,} registros")
    except Exception as e:
        print(f"  {table}: Error - {e}")
    sys.stdout.flush()

remote_cursor.close()
local_cursor.close()
remote_conn.close()
local_conn.close()

print("\n✅ ANÁLISIS COMPLETADO")
sys.stdout.flush()
