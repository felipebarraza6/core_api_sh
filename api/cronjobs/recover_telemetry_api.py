#!/usr/bin/env python3
"""
SCRIPT: Recuperar backlog de telemetry_api
Sincroniza tablas en orden correcto de dependencias FK, luego mediciones.
Uso: python recover_telemetry_api.py
"""

import os
import time
import psycopg2
import psycopg2.extras


# ORDEN CORRECTO DE DEPENDENCIAS (padres primero, hijos después)
SYNC_ORDER = [
    # Nivel 1: Sin dependencias
    'core_client',
    'core_typefilecatchment',
    'core_registerpersons',
    # Nivel 2: Depende de nivel 1
    'core_user',
    'core_projectcatchments',  # Padre de catchmentpoint
    'core_schemescatchment',   # Padre de variable
    # Nivel 3: Depende de nivel 2
    'core_variable',           # Depende de schemescatchment
    'core_catchmentpoint',     # Depende de user, project
    # Nivel 4: Depende de nivel 3
    'core_dgadataconfigcatchment',
    'core_profiledataconfigcatchment',
    'core_profileikolucatchment',
    'core_notificationscatchment',
    # Nivel 5: Tablas de relación
    'core_user_groups',
    'core_user_user_permissions',
    'core_catchmentpoint_users_viewers',
    'core_schemescatchment_points_catchment',
    'core_responsenotificationscatchment',
    'core_filecatchment',
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

CLUSTER_TELEMETRY_API = {
    "host": os.environ.get("CLUSTER_DB_HOST"),
    "port": os.environ.get("CLUSTER_DB_PORT", "25060"),
    "user": os.environ.get("CLUSTER_DB_USER", "api_principal"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD"),
    "database": "telemetry_api",
    "sslmode": "require",
}

BATCH_SIZE = 25000


def get_table_columns(cursor, table_name):
    """Obtener columnas de una tabla"""
    cursor.execute(f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}' 
        ORDER BY ordinal_position
    """)
    return [row[0] for row in cursor.fetchall()]


def sync_table_upsert(local_cursor, cluster_conn, cluster_cursor, table_name):
    """Sincronizar tabla usando UPSERT con manejo robusto de errores"""
    try:
        # Verificar existencia en local
        local_cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = %s AND table_schema = 'public'
            )
        """, (table_name,))
        
        if not local_cursor.fetchone()[0]:
            return 0, "no existe en local"
        
        # Verificar existencia en cluster
        cluster_cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = %s AND table_schema = 'public'
            )
        """, (table_name,))
        
        if not cluster_cursor.fetchone()[0]:
            return 0, "no existe en cluster"
        
        # Obtener columnas
        columns = get_table_columns(local_cursor, table_name)
        if not columns:
            return 0, "sin columnas"
        
        has_id = 'id' in columns
        
        # Contar local
        local_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        local_count = local_cursor.fetchone()[0]
        
        if local_count == 0:
            return 0, "vacía"
        
        # Obtener todos los registros locales
        local_cursor.execute(f"SELECT * FROM {table_name} ORDER BY {'id' if has_id else '1'}")
        rows = local_cursor.fetchall()
        
        # Construir query
        columns_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        
        if has_id:
            # Columnas para update (excluir id)
            update_cols = [c for c in columns if c != 'id']
            if update_cols:
                update_str = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
                insert_query = f"""
                    INSERT INTO {table_name} ({columns_str}) 
                    VALUES ({placeholders})
                    ON CONFLICT (id) DO UPDATE SET {update_str}
                """
            else:
                insert_query = f"""
                    INSERT INTO {table_name} ({columns_str}) 
                    VALUES ({placeholders})
                    ON CONFLICT (id) DO NOTHING
                """
        else:
            insert_query = f"""
                INSERT INTO {table_name} ({columns_str}) 
                VALUES ({placeholders})
            """
        
        # Insertar registros uno por uno para manejar errores
        inserted = 0
        errors = 0
        for row in rows:
            try:
                cluster_cursor.execute(insert_query, row)
                inserted += 1
            except Exception as e:
                errors += 1
                if errors <= 2:  # Solo mostrar primeros errores
                    print(f"      Error: {str(e)[:80]}")
                cluster_conn.rollback()
        
        cluster_conn.commit()
        return inserted, f"{inserted}/{local_count}"
        
    except Exception as e:
        return 0, str(e)[:60]


def sync_interaction_detail(local_cursor, cluster_conn, cluster_cursor):
    """Sincronizar InteractionDetail en lotes"""
    print("\n" + "=" * 50)
    print("PASO 2: SINCRONIZAR INTERACTIONDETAIL")
    print("=" * 50)
    
    # Contar registros
    local_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail")
    local_count = local_cursor.fetchone()[0]
    
    cluster_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail")
    cluster_count = cluster_cursor.fetchone()[0]
    
    print(f"📊 Local: {local_count:,}")
    print(f"📊 Cluster: {cluster_count:,}")
    
    if local_count <= cluster_count:
        print("✅ Ya sincronizado")
        return True
    
    # Obtener max ID del cluster
    cluster_cursor.execute("SELECT COALESCE(MAX(id), 0) FROM core_interactiondetail")
    max_cluster_id = cluster_cursor.fetchone()[0]
    
    # Obtener registros faltantes
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
    total_records = len(missing_records)
    
    if total_records == 0:
        print("✅ No hay registros nuevos")
        return True
    
    print(f"📥 Migrando {total_records:,} registros...")
    
    insert_query = """
        INSERT INTO core_interactiondetail 
        (id, created, modified, date_time_medition, date_time_last_logger,
         flow, total, total_diff, total_today_diff, nivel, water_table,
         send_dga, return_dga, n_voucher, is_error, catchment_point_id,
         notification_id, pulses, days_not_conection)
        VALUES %s
        ON CONFLICT (id) DO NOTHING
    """
    
    start_time = time.time()
    total_inserted = 0
    total_batches = (total_records + BATCH_SIZE - 1) // BATCH_SIZE
    
    for i in range(0, total_records, BATCH_SIZE):
        batch = missing_records[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        
        try:
            psycopg2.extras.execute_values(
                cluster_cursor, insert_query, batch, page_size=1000
            )
            cluster_conn.commit()
            total_inserted += len(batch)
            
            elapsed = time.time() - start_time
            rate = total_inserted / elapsed if elapsed > 0 else 0
            
            print(f"  ✅ Batch {batch_num}/{total_batches}: {total_inserted:,} | {rate:.0f}/s")
                  
        except Exception as e:
            print(f"  ⚠️ Batch {batch_num}: {str(e)[:80]}")
            cluster_conn.rollback()
    
    print(f"\n🎉 Migrados: {total_inserted:,}")
    return True


def recover_telemetry_api():
    """Recuperación completa de telemetry_api"""
    print("=" * 60)
    print("RECUPERACIÓN DE TELEMETRY_API")
    print("Sincroniza tablas en orden de dependencias FK")
    print("=" * 60)
    
    try:
        # Conectar
        print("\n📦 Conectando...")
        local_conn = psycopg2.connect(**LOCAL_DB)
        local_cursor = local_conn.cursor()
        
        cluster_conn = psycopg2.connect(**CLUSTER_TELEMETRY_API)
        cluster_cursor = cluster_conn.cursor()
        print("✅ Conexiones establecidas")
        
        # PASO 1: Tablas operativas en orden de dependencias
        print("\n" + "=" * 50)
        print("PASO 1: SINCRONIZAR TABLAS OPERATIVAS")
        print("(en orden de dependencias FK)")
        print("=" * 50)
        
        for table_name in SYNC_ORDER:
            count, status = sync_table_upsert(local_cursor, cluster_conn, cluster_cursor, table_name)
            if count > 0 or status not in ["vacía", "no existe en local"]:
                print(f"  {'✅' if count > 0 else '⏭️'} {table_name}: {status}")
        
        # PASO 2: InteractionDetail
        sync_interaction_detail(local_cursor, cluster_conn, cluster_cursor)
        
        # Verificación final
        print("\n" + "=" * 50)
        print("VERIFICACIÓN FINAL")
        print("=" * 50)
        
        for table in ['core_catchmentpoint', 'core_interactiondetail']:
            local_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            local_count = local_cursor.fetchone()[0]
            
            cluster_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            cluster_count = cluster_cursor.fetchone()[0]
            
            status = "✅" if cluster_count >= local_count * 0.95 else "⚠️"
            print(f"  {status} {table}: Local {local_count:,} | Cluster {cluster_count:,}")
        
        # Cerrar
        cluster_cursor.close()
        cluster_conn.close()
        local_cursor.close()
        local_conn.close()
        
        print("\n✅ Recuperación completada")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = recover_telemetry_api()
    exit(0 if success else 1)
