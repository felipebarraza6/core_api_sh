#!/usr/bin/env python3
"""
SCRIPT DE RESTAURACIÓN DESDE CLUSTER
=====================================
Restaura la base de datos local desde el cluster de DigitalOcean.

Orden de restauración:
1. telemetry_api: Tablas de configuración (puntos, usuarios, DGA config, etc.)
2. data_store_telemetry: core_interactiondetail (mediciones más recientes)

Uso:
    python maintenance/restore_from_cluster.py
"""

import os
import sys
import psycopg2
from datetime import datetime

# Configuración del cluster
CLUSTER_CONFIG = {
    "host": os.environ.get("CLUSTER_DB_HOST", "db-postgresql-nyc3-22918-do-user-7500906-0.m.db.ondigitalocean.com"),
    "port": os.environ.get("CLUSTER_DB_PORT", "25060"),
    "user": os.environ.get("CLUSTER_DB_USER", "api_principal"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD", "AVNS_HF8s0ddit--a4cZSRxy"),
    "sslmode": "require",
}

# Base de datos local
LOCAL_DB = {
    "host": os.environ.get("LOCAL_DB_HOST", "localhost"),
    "port": os.environ.get("LOCAL_DB_PORT", "5432"),
    "user": os.environ.get("LOCAL_DB_USER", "smarthydro_user"),
    "password": os.environ.get("LOCAL_DB_PASSWORD", "smarthydro_password_2025"),
    "database": os.environ.get("LOCAL_DB_NAME", "smarthydro_prod"),
}

# Tablas de configuración (sin interactiondetail)
CONFIG_TABLES = [
    "core_client",
    "core_variable",
    "core_typefilecatchment",
    "core_user",
    "core_user_groups",
    "core_user_user_permissions",
    "core_catchmentpoint",
    "core_catchmentpoint_users_viewers",
    "core_dgadataconfigcatchment",
    "core_profiledataconfigcatchment",
    "core_profileikolucatchment",
    "core_notificationscatchment",
    "core_responsenotificationscatchment",
    "core_filecatchment",
    "core_registerpersons",
    "core_projectcatchments",
    "core_schemescatchment",
    "core_schemescatchment_points_catchment",
]

def log(msg):
    """Log con timestamp"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def connect_cluster(database):
    """Conectar a base de datos del cluster"""
    config = {**CLUSTER_CONFIG, "database": database}
    return psycopg2.connect(**config)

def connect_local():
    """Conectar a base de datos local"""
    return psycopg2.connect(**LOCAL_DB)

def get_table_count(cursor, table):
    """Obtener cantidad de registros en una tabla"""
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    except:
        return 0

def truncate_local_tables(local_cursor):
    """Vaciar tablas locales en orden inverso (por foreign keys)"""
    log("🗑️  Vaciando tablas locales...")

    # Deshabilitar triggers temporalmente
    local_cursor.execute("SET session_replication_role = 'replica';")

    # Vaciar en orden inverso
    for table in reversed(CONFIG_TABLES + ["core_interactiondetail"]):
        try:
            local_cursor.execute(f"TRUNCATE TABLE {table} CASCADE;")
            log(f"   ✓ {table} vaciada")
        except Exception as e:
            log(f"   ⚠ {table}: {e}")

    # Rehabilitar triggers
    local_cursor.execute("SET session_replication_role = 'origin';")

def copy_table(source_cursor, local_cursor, table, source_db):
    """Copiar una tabla completa del cluster a local"""
    try:
        # Obtener columnas
        source_cursor.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}'
            ORDER BY ordinal_position
        """)
        columns = [row[0] for row in source_cursor.fetchall()]

        if not columns:
            log(f"   ⚠ {table}: sin columnas")
            return 0

        columns_str = ", ".join(f'"{c}"' for c in columns)

        # Obtener datos
        source_cursor.execute(f"SELECT {columns_str} FROM {table}")
        rows = source_cursor.fetchall()

        if not rows:
            log(f"   ⚠ {table}: sin datos")
            return 0

        # Insertar en local
        placeholders = ", ".join(["%s"] * len(columns))
        insert_sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

        local_cursor.executemany(insert_sql, rows)

        return len(rows)
    except Exception as e:
        log(f"   ❌ {table}: {e}")
        return 0

def copy_interactiondetail_batched(source_cursor, local_cursor, batch_size=10000):
    """Copiar core_interactiondetail en batches"""
    table = "core_interactiondetail"

    # Obtener columnas
    source_cursor.execute(f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = '{table}'
        ORDER BY ordinal_position
    """)
    columns = [row[0] for row in source_cursor.fetchall()]
    columns_str = ", ".join(f'"{c}"' for c in columns)

    # Obtener total
    source_cursor.execute(f"SELECT COUNT(*) FROM {table}")
    total = source_cursor.fetchone()[0]

    log(f"📊 Copiando {total:,} registros de {table}...")

    # Copiar en batches
    offset = 0
    copied = 0

    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

    while offset < total:
        source_cursor.execute(f"""
            SELECT {columns_str} FROM {table}
            ORDER BY id
            LIMIT {batch_size} OFFSET {offset}
        """)
        rows = source_cursor.fetchall()

        if not rows:
            break

        local_cursor.executemany(insert_sql, rows)
        copied += len(rows)
        offset += batch_size

        progress = (copied / total) * 100
        log(f"   📈 {copied:,}/{total:,} ({progress:.1f}%)")

    return copied

def restore_config_from_telemetry_api(local_conn, local_cursor):
    """Restaurar configuración desde telemetry_api"""
    log("=" * 50)
    log("FASE 1: Restaurar configuración desde telemetry_api")
    log("=" * 50)

    cluster_conn = connect_cluster("telemetry_api")
    cluster_cursor = cluster_conn.cursor()

    total_copied = 0

    for table in CONFIG_TABLES:
        count = copy_table(cluster_cursor, local_cursor, table, "telemetry_api")
        if count > 0:
            log(f"   ✓ {table}: {count:,} registros")
            total_copied += count

    local_conn.commit()
    cluster_conn.close()

    log(f"✅ Configuración restaurada: {total_copied:,} registros")
    return total_copied

def restore_telemetry_from_data_store(local_conn, local_cursor):
    """Restaurar mediciones desde data_store_telemetry"""
    log("=" * 50)
    log("FASE 2: Restaurar mediciones desde data_store_telemetry")
    log("=" * 50)

    cluster_conn = connect_cluster("data_store_telemetry")
    cluster_cursor = cluster_conn.cursor()

    # Copiar interactiondetail en batches
    count = copy_interactiondetail_batched(cluster_cursor, local_cursor)

    local_conn.commit()
    cluster_conn.close()

    log(f"✅ Mediciones restauradas: {count:,} registros")
    return count

def verify_restoration(local_cursor):
    """Verificar que la restauración fue exitosa"""
    log("=" * 50)
    log("VERIFICACIÓN FINAL")
    log("=" * 50)

    # Verificar conteos
    local_cursor.execute("SELECT COUNT(*) FROM core_catchmentpoint")
    points = local_cursor.fetchone()[0]

    local_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail")
    records = local_cursor.fetchone()[0]

    local_cursor.execute("SELECT MIN(created), MAX(created) FROM core_interactiondetail")
    min_date, max_date = local_cursor.fetchone()

    log(f"📊 Puntos de captación: {points}")
    log(f"📊 Registros telemetría: {records:,}")
    log(f"📊 Rango de fechas: {min_date} a {max_date}")

    return points, records

def main():
    log("=" * 60)
    log("🔄 RESTAURACIÓN DE BASE DE DATOS DESDE CLUSTER")
    log("=" * 60)

    # Verificar conexiones
    log("\n🔌 Verificando conexiones...")

    try:
        cluster_conn = connect_cluster("telemetry_api")
        cluster_conn.close()
        log("   ✓ telemetry_api: OK")
    except Exception as e:
        log(f"   ❌ telemetry_api: {e}")
        return False

    try:
        cluster_conn = connect_cluster("data_store_telemetry")
        cluster_conn.close()
        log("   ✓ data_store_telemetry: OK")
    except Exception as e:
        log(f"   ❌ data_store_telemetry: {e}")
        return False

    try:
        local_conn = connect_local()
        local_cursor = local_conn.cursor()
        log("   ✓ Local: OK")
    except Exception as e:
        log(f"   ❌ Local: {e}")
        return False

    # Mostrar estado actual
    log("\n📊 Estado actual de la DB local:")
    current_records = get_table_count(local_cursor, "core_interactiondetail")
    current_points = get_table_count(local_cursor, "core_catchmentpoint")
    log(f"   Puntos: {current_points}, Registros: {current_records:,}")

    # Confirmar
    print("\n" + "=" * 60)
    print("⚠️  ADVERTENCIA: Esto BORRARÁ todos los datos locales actuales")
    print("   y los reemplazará con los datos del cluster.")
    print("=" * 60)

    confirm = input("\n¿Continuar? (escribir 'SI' para confirmar): ")
    if confirm.upper() != "SI":
        log("❌ Restauración cancelada")
        return False

    # Vaciar tablas locales
    log("\n")
    truncate_local_tables(local_cursor)
    local_conn.commit()

    # Restaurar configuración
    log("\n")
    restore_config_from_telemetry_api(local_conn, local_cursor)

    # Restaurar mediciones
    log("\n")
    restore_telemetry_from_data_store(local_conn, local_cursor)

    # Verificar
    log("\n")
    verify_restoration(local_cursor)

    # Reset secuencias
    log("\n🔧 Reseteando secuencias...")
    local_cursor.execute("""
        SELECT setval(pg_get_serial_sequence('core_interactiondetail', 'id'),
                      (SELECT MAX(id) FROM core_interactiondetail));
    """)
    local_cursor.execute("""
        SELECT setval(pg_get_serial_sequence('core_catchmentpoint', 'id'),
                      (SELECT MAX(id) FROM core_catchmentpoint));
    """)
    local_conn.commit()

    log("\n" + "=" * 60)
    log("✅ RESTAURACIÓN COMPLETADA")
    log("=" * 60)
    log("\nPróximos pasos:")
    log("1. Ejecutar migraciones: python manage.py migrate")
    log("2. Reiniciar servicios: docker-compose restart django cron")

    local_conn.close()
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
