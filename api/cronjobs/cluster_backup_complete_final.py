#!/usr/bin/env python3
"""
RESPALDO DUAL SIMPLIFICADO
==========================
telemetry_api      → Solo datos operativos (config)
data_store_telemetry → Solo mediciones (InteractionDetail)
"""

import os
import time
import psycopg2
import psycopg2.extras

# TABLAS OPERATIVAS (solo para telemetry_api)
OPERATIONAL_TABLES = [
    'core_client',
    'core_user', 
    'core_user_groups',
    'core_user_user_permissions',
    'core_typefilecatchment',
    'core_registerpersons',
    'core_projectcatchments',
    'core_schemescatchment',
    'core_variable',
    'core_catchmentpoint',
    'core_dgadataconfigcatchment',
    'core_profiledataconfigcatchment',
    'core_profileikolucatchment', 
    'core_filecatchment',
    'core_catchmentpoint_users_viewers',
    'core_schemescatchment_points_catchment',
    'core_notificationscatchment',
    'core_responsenotificationscatchment'
]


def load_env():
    """Cargar variables de entorno desde archivo .env"""
    env_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
    )
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value


load_env()

LOCAL_DB = {
    "host": os.environ.get("LOCAL_DB_HOST", "postgres"),
    "port": os.environ.get("LOCAL_DB_PORT", "5432"),
    "user": os.environ.get("LOCAL_DB_USER", "smarthydro_user"),
    "password": os.environ.get("LOCAL_DB_PASSWORD", ""),
    "database": os.environ.get("LOCAL_DB_NAME", "smarthydro_prod"),
}

# telemetry_api = Solo config operativa
CLUSTER_DB_CONFIG = {
    "host": os.environ.get("CLUSTER_DB_HOST"),
    "port": os.environ.get("CLUSTER_DB_PORT", "25060"),
    "user": os.environ.get("CLUSTER_DB_USER", "api_principal"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD", ""),
    "database": os.environ.get("CLUSTER_DB_NAME", "telemetry_api"),
    "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
}

# data_store_telemetry = Solo mediciones
CLUSTER_DB_TELEMETRY = {
    "host": os.environ.get("CLUSTER_DB_HOST"),
    "port": os.environ.get("CLUSTER_DB_PORT", "25060"),
    "user": os.environ.get("CLUSTER_DB_USER_BACKUP", "api_principal"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD_BACKUP", ""),
    "database": "data_store_telemetry",
    "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
}


def backup_operational_to_telemetry_api(local_cursor, cluster_conn, cluster_cursor):
    """Respaldar tablas operativas a telemetry_api"""
    print("🔧 telemetry_api: Respaldando configuración operativa...")
    
    success_count = 0
    
    for table_name in OPERATIONAL_TABLES:
        try:
            # Verificar existencia
            local_cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s AND table_schema = 'public'
                )
            """, (table_name,))
            
            if not local_cursor.fetchone()[0]:
                continue
            
            # Contar local
            local_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            local_count = local_cursor.fetchone()[0]
            
            if local_count == 0:
                success_count += 1
                continue
            
            # Obtener columnas
            local_cursor.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                ORDER BY ordinal_position
            """)
            columns = [row[0] for row in local_cursor.fetchall()]
            
            # Obtener max ID en cluster
            try:
                cluster_cursor.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}")
                max_cluster_id = cluster_cursor.fetchone()[0]
            except:
                max_cluster_id = 0
            
            # Obtener registros nuevos
            local_cursor.execute(f"SELECT * FROM {table_name} WHERE id > {max_cluster_id} ORDER BY id")
            rows = local_cursor.fetchall()
            
            if not rows:
                success_count += 1
                continue
            
            # INSERT con ON CONFLICT
            columns_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            update_cols = [c for c in columns if c != 'id']
            update_str = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols]) if update_cols else "id = EXCLUDED.id"
            
            insert_query = f"""
                INSERT INTO {table_name} ({columns_str}) 
                VALUES ({placeholders})
                ON CONFLICT (id) DO UPDATE SET {update_str}
            """
            
            inserted = 0
            for row in rows:
                try:
                    cluster_cursor.execute(insert_query, row)
                    inserted += 1
                except:
                    pass
            
            cluster_conn.commit()
            
            if inserted > 0:
                print(f"  ✅ {table_name}: +{inserted} nuevos")
            
            success_count += 1
            
        except Exception as e:
            print(f"  ⚠️ {table_name}: {str(e)[:50]}")
    
    print(f"✅ telemetry_api: {success_count}/{len(OPERATIONAL_TABLES)} tablas procesadas")
    return success_count


def backup_telemetry_to_data_store(local_cursor, cluster_conn, cluster_cursor, local_total):
    """Respaldar InteractionDetail a data_store_telemetry"""
    print("📊 data_store_telemetry: Respaldando mediciones...")
    
    try:
        cluster_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        cluster_total = cluster_cursor.fetchone()[0]
    except:
        cluster_total = 0
    
    missing_count = local_total - cluster_total
    print(f"  Local: {local_total:,} | Cluster: {cluster_total:,} | Pendientes: {missing_count:,}")
    
    if missing_count <= 0:
        print("✅ data_store_telemetry: Ya sincronizado")
        return True
    
    # Limpiar huérfanos si hay
    try:
        cluster_cursor.execute("SELECT id FROM core_interactiondetail ORDER BY id;")
        cluster_ids = set(row[0] for row in cluster_cursor.fetchall())
        
        local_cursor.execute("SELECT id FROM core_interactiondetail ORDER BY id;")
        local_ids = set(row[0] for row in local_cursor.fetchall())
        
        orphan_ids = cluster_ids - local_ids
        if orphan_ids and len(orphan_ids) < 10000:
            orphan_list = list(orphan_ids)
            for i in range(0, len(orphan_list), 1000):
                batch = orphan_list[i:i + 1000]
                placeholders = ",".join(["%s"] * len(batch))
                cluster_cursor.execute(f"DELETE FROM core_interactiondetail WHERE id IN ({placeholders})", batch)
            cluster_conn.commit()
            print(f"  🧹 Eliminados {len(orphan_ids)} huérfanos")
    except:
        pass
    
    # Obtener registros faltantes
    cluster_cursor.execute("SELECT COALESCE(MAX(id), 0) FROM core_interactiondetail;")
    max_cluster_id = cluster_cursor.fetchone()[0]
    
    local_cursor.execute("""
        SELECT id, created, modified, date_time_medition, date_time_last_logger,
               flow, total, total_diff, total_today_diff, nivel, water_table,
               send_dga, return_dga, n_voucher, is_error, catchment_point_id,
               notification_id, pulses, days_not_conection
        FROM core_interactiondetail
        WHERE id > %s
        ORDER BY id
    """, (max_cluster_id,))
    
    missing_records = local_cursor.fetchall()
    
    if not missing_records:
        print("✅ data_store_telemetry: Sin registros nuevos")
        return True
    
    # Migrar en lotes de 50K
    insert_query = """
        INSERT INTO core_interactiondetail 
        (id, created, modified, date_time_medition, date_time_last_logger,
         flow, total, total_diff, total_today_diff, nivel, water_table,
         send_dga, return_dga, n_voucher, is_error, catchment_point_id,
         notification_id, pulses, days_not_conection)
        VALUES %s
        ON CONFLICT (id) DO NOTHING
    """
    
    BATCH_SIZE = 50000
    total_records = len(missing_records)
    total_inserted = 0
    start_time = time.time()
    
    for i in range(0, total_records, BATCH_SIZE):
        batch = missing_records[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (total_records + BATCH_SIZE - 1) // BATCH_SIZE
        
        try:
            psycopg2.extras.execute_values(
                cluster_cursor, insert_query, batch, page_size=1000
            )
            cluster_conn.commit()
            total_inserted += len(batch)
            print(f"  ✅ Batch {batch_num}/{total_batches}: {len(batch):,} registros")
        except Exception as e:
            print(f"  ⚠️ Batch {batch_num}: {str(e)[:60]}")
            cluster_conn.rollback()
    
    elapsed = time.time() - start_time
    rate = total_inserted / elapsed if elapsed > 0 else 0
    print(f"🚀 data_store_telemetry: {total_inserted:,} en {elapsed:.1f}s ({rate:.0f} reg/s)")
    
    return total_inserted > 0


def find_and_migrate_missing():
    """Respaldo dual simplificado"""
    print("=" * 50)
    print("RESPALDO DUAL SIMPLIFICADO")
    print("telemetry_api → Config operativa")
    print("data_store_telemetry → Mediciones")
    print("=" * 50)
    print()
    
    try:
        # Conectar local
        local_conn = psycopg2.connect(**LOCAL_DB)
        local_cursor = local_conn.cursor()
        
        local_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        local_total = local_cursor.fetchone()[0]
        print(f"✅ Local: {local_total:,} registros InteractionDetail")
        print()
        
        results = []
        
        # === TELEMETRY_API: Solo config ===
        print("🔄 RESPALDO 1: telemetry_api (config)")
        try:
            config_conn = psycopg2.connect(**CLUSTER_DB_CONFIG)
            config_cursor = config_conn.cursor()
            
            result1 = backup_operational_to_telemetry_api(local_cursor, config_conn, config_cursor)
            results.append(("telemetry_api (config)", result1 > 0))
            
            config_cursor.close()
            config_conn.close()
        except Exception as e:
            print(f"❌ telemetry_api: {e}")
            results.append(("telemetry_api (config)", False))
        
        print()
        
        # === DATA_STORE_TELEMETRY: Solo mediciones ===
        print("🔄 RESPALDO 2: data_store_telemetry (mediciones)")
        try:
            telem_conn = psycopg2.connect(**CLUSTER_DB_TELEMETRY)
            telem_cursor = telem_conn.cursor()
            
            result2 = backup_telemetry_to_data_store(local_cursor, telem_conn, telem_cursor, local_total)
            results.append(("data_store_telemetry (mediciones)", result2))
            
            telem_cursor.close()
            telem_conn.close()
        except Exception as e:
            print(f"❌ data_store_telemetry: {e}")
            results.append(("data_store_telemetry (mediciones)", False))
        
        local_cursor.close()
        local_conn.close()
        
        # Resumen
        print()
        print("=" * 40)
        print("RESUMEN RESPALDO DUAL")
        print("=" * 40)
        
        for db_name, result in results:
            status = "✅ OK" if result else "❌ FALLÓ"
            print(f"  {status} {db_name}")
        
        return all(r for _, r in results)
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def run():
    """Función para cron"""
    try:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando respaldo dual...")
        result = find_and_migrate_missing()
        status = "exitoso" if result else "parcial"
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Respaldo dual {status}")
        return result
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error: {e}")
        return False


if __name__ == "__main__":
    find_and_migrate_missing()
