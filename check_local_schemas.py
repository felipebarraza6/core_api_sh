#!/usr/bin/env python3
"""Check actual local database schemas"""
import psycopg2
import sys

print("=" * 60)
print("ESQUEMAS LOCALES")
print("=" * 60)
sys.stdout.flush()

local_conn = psycopg2.connect(
    host='postgres',
    port=5432,
    user='smarthydro_user',
    password='smarthydro_password_2025',
    database='smarthydro_prod'
)

local_cursor = local_conn.cursor()

tables = [
    'core_client',
    'core_projectcatchments',
    'core_catchmentpoint',
    'core_schemescatchment',
    'core_variable'
]

for table in tables:
    print(f"\n=== {table.upper()} ===")
    sys.stdout.flush()

    local_cursor.execute(f"""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = '{table}'
        ORDER BY ordinal_position
    """)

    for col_name, col_type, nullable in local_cursor.fetchall():
        null_str = "NULL" if nullable == 'YES' else "NOT NULL"
        print(f"  {col_name}: {col_type} {null_str}")
    sys.stdout.flush()

local_cursor.close()
local_conn.close()

print("\n✅ COMPLETADO")
sys.stdout.flush()
