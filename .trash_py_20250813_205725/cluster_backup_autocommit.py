#!/usr/bin/env python3

import os
import time
import psycopg2
import psycopg2.extras

# ORDEN DE TABLAS PARA RESPALDO (sin tocar InteractionDetail que ya funciona)
CORE_OPERATIONAL_TABLES = [
    'core_client',
    'core_user', 
    'core_user_groups',
    'core_user_user_permissions',
    'core_typefilecatchment',
    'core_registerpersons',
    'core_variable',
    'core_schemescatchment',
    'core_catchmentpoint',
    'core_dgadataconfigcatchment',
    'core_profiledataconfigcatchment',
    'core_profileikolucatchment', 
    'core_filecatchment',
    'core_catchmentpoint_users_viewers',
    'core_schemescatchment_points_catchment',
    'core_projectcatchments',
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

CLUSTER_DB_PRIMARY = {
    "host": os.environ.get("CLUSTER_DB_HOST", "db-postgresql.com"),
    "port": os.environ.get("CLUSTER_DB_PORT", "123"),
    "user": os.environ.get("CLUSTER_DB_USER", "admin"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD", ""),
    "database": os.environ.get("CLUSTER_DB_NAME", "telemetry_api"),
    "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
}

CLUSTER_DB_BACKUP = {
    "host": os.environ.get("CLUSTER_DB_HOST", "db-postgresql.com"),
    "port": os.environ.get("CLUSTER_DB_PORT", "123"),
    "user": os.environ.get("CLUSTER_DB_USER_BACKUP", "data_store_telemetry"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD_BACKUP", ""),
    "database": "data_store_telemetry",
    "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
}

def create_core_table_if_not_exists(local_cursor, cluster_cursor, table_name, db_name):
    """Crear tabla core_ si no existe, copiando estructura del local"""
    try:
        # Verificar si existe en cluster
        cluster_cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = %s AND table_schema = 'public'
            )
        """, (table_name,))
        
        if cluster_cursor.fetchone()[0]:
            return True
        
        # Obtener CREATE TABLE simplificado
        local_cursor.execute(f"""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' AND table_schema = 'public'
            ORDER BY ordinal_position
        """)
        
        columns_info = local_cursor.fetchall()
        if not columns_info:
            return False
        
        # Construir CREATE TABLE básico
        columns_def = []
        for col_name, data_type, is_nullable, col_default in columns_info:
            col_def = f"{col_name} "
            
            # Mapear tipos básicos
            if 'character varying' in data_type:
                col_def += "TEXT"
            elif 'integer' in data_type:
                if col_name == 'id':
                    col_def += "SERIAL PRIMARY KEY"
                else:
                    col_def += "INTEGER"
            elif 'bigint' in data_type:
                col_def += "BIGINT"
            elif 'boolean' in data_type:
                col_def += "BOOLEAN"
            elif 'timestamp' in data_type:
                col_def += "TIMESTAMP WITH TIME ZONE"
            elif 'numeric' in data_type or 'decimal' in data_type:
                col_def += "NUMERIC"
            elif 'text' in data_type:
                col_def += "TEXT"
            else:
                col_def += "TEXT"  # Fallback
            
            if is_nullable == 'NO' and col_name != 'id':
                col_def += " NOT NULL"
            
            columns_def.append(col_def)
        
        create_sql = f"CREATE TABLE {table_name} ({', '.join(columns_def)})"
        
        # Ejecutar creación
        cluster_cursor.execute(create_sql)
        print(f"✅ {db_name}: {table_name} creada")
        return True
        
    except Exception as e:
        print(f"❌ {db_name}: Error creando {table_name}: {e}")
        return False

def ensure_core_tables_exist(local_cursor, cluster_cursor, db_name):
    """Asegurar que todas las tablas core_ existen"""
    print(f"🔧 {db_name}: Verificando tablas core_...")
    
    tables_to_check = CORE_OPERATIONAL_TABLES + ['core_interactiondetail']
    success_count = 0
    
    for table_name in tables_to_check:
        if create_core_table_if_not_exists(local_cursor, cluster_cursor, table_name, db_name):
            success_count += 1
    
    print(f"✅ {db_name}: {success_count}/{len(tables_to_check)} tablas verificadas")
    return success_count == len(tables_to_check)

def backup_operational_tables(local_cursor, cluster_cursor, db_name):
    """Respaldar tablas operativas core_"""
    print(f"🔧 {db_name}: Respaldando tablas operativas...")
    
    success_count = 0
    
    for table_name in CORE_OPERATIONAL_TABLES:
        try:
            # Verificar si existe en local
            local_cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s AND table_schema = 'public'
                )
            """, (table_name,))
            
            if not local_cursor.fetchone()[0]:
                continue
            
            # Contar registros
            local_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            local_count = local_cursor.fetchone()[0]
            
            if local_count == 0:
                success_count += 1
                continue
            
            # Truncar tabla cluster
            try:
                cluster_cursor.execute(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE")
            except:
                pass
            
            # Copiar datos
            local_cursor.execute(f"SELECT * FROM {table_name} ORDER BY id")
            rows = local_cursor.fetchall()
            
            if rows:
                # Obtener columnas
                local_cursor.execute(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}' 
                    ORDER BY ordinal_position
                """)
                columns = [row[0] for row in local_cursor.fetchall()]
                columns_str = ", ".join(columns)
                placeholders = ", ".join(["%s"] * len(columns))
                
                insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                
                inserted = 0
                for row in rows:
                    try:
                        cluster_cursor.execute(insert_query, row)
                        inserted += 1
                    except:
                        pass
                
                print(f"✅ {db_name}: {table_name} - {inserted} registros")
            
            success_count += 1
            
        except Exception as e:
            print(f"❌ {db_name}: Error en {table_name}: {e}")
    
    return success_count

def backup_to_database(cluster_db_config, db_name):
    """Conectar a base del cluster"""
    print(f"=== CONECTANDO A {db_name.upper()} ===")
    try:
        cluster_conn = psycopg2.connect(**cluster_db_config)
        cluster_conn.autocommit = True
        cluster_cursor = cluster_conn.cursor()
        
        try:
            cluster_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
            cluster_total = cluster_cursor.fetchone()[0]
            print(f"✅ {db_name}: {cluster_total:,} registros InteractionDetail")
        except:
            cluster_total = 0
            print(f"✅ {db_name}: Conectado (InteractionDetail no existe aún)")
        
        return cluster_conn, cluster_cursor, cluster_total
    except Exception as e:
        print(f"❌ ERROR conectando a {db_name}: {e}")
        return None, None, 0

def sync_to_database(local_conn, local_cursor, cluster_conn, cluster_cursor, db_name, local_total):
    """Sincronización completa: tablas core_ + InteractionDetail"""
    print(f"=== SINCRONIZANDO {db_name.upper()} ===")
    
    try:
        # PASO 0: Crear tablas si no existen
        print(f"🔧 {db_name}: PASO 0 - Verificando estructura")
        if not ensure_core_tables_exist(local_cursor, cluster_cursor, db_name):
            print(f"❌ {db_name}: Error en estructura de tablas")
            return False
        cluster_conn.commit()
        
        # PASO 1: Respaldar tablas operativas
        print(f"🔧 {db_name}: PASO 1 - Tablas operativas")
        operational_success = backup_operational_tables(local_cursor, cluster_cursor, db_name)
        cluster_conn.commit()
        print(f"✅ {db_name}: {operational_success} tablas operativas procesadas")
        
        # PASO 2: InteractionDetail (tu código original)
        print(f"📊 {db_name}: PASO 2 - InteractionDetail")
        
        cluster_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        cluster_total = cluster_cursor.fetchone()[0]
        missing_count = local_total - cluster_total
        
        print(f"📊 {db_name}: Local {local_total:,} vs Cluster {cluster_total:,}")
        print(f"📊 FALTANTES: {missing_count:,}")
        
        if missing_count <= 0:
            print(f"✅ {db_name}: InteractionDetail ya sincronizada")
            return True
        
        # Limpiar huérfanos
        print(f"🧹 {db_name}: Limpiando huérfanos...")
        cluster_cursor.execute("SELECT id FROM core_interactiondetail ORDER BY id;")
        cluster_ids = set(row[0] for row in cluster_cursor.fetchall())
        
        local_cursor.execute("SELECT id FROM core_interactiondetail ORDER BY id;")
        local_ids = set(row[0] for row in local_cursor.fetchall())
        
        orphan_ids = cluster_ids - local_ids
        if orphan_ids:
            print(f"🗑️ {db_name}: Eliminando {len(orphan_ids)} huérfanos...")
            orphan_list = list(orphan_ids)
            for i in range(0, len(orphan_list), 1000):
                batch = orphan_list[i:i + 1000]
                placeholders = ",".join(["%s"] * len(batch))
                cluster_cursor.execute(f"DELETE FROM core_interactiondetail WHERE id IN ({placeholders})", batch)
            cluster_conn.commit()
        
        # Buscar registros faltantes
        cluster_cursor.execute("SELECT MAX(id) FROM core_interactiondetail;")
        max_id_result = cluster_cursor.fetchone()
        max_cluster_id = max_id_result[0] if max_id_result[0] else 0
        
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
        
        if missing_records:
            print(f"📥 {db_name}: Migrando {len(missing_records):,} registros...")
            
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
            psycopg2.extras.execute_values(
                cluster_cursor, insert_query, missing_records, page_size=1000
            )
            cluster_conn.commit()
            end_time = time.time()
            
            rate = len(missing_records) / (end_time - start_time) if end_time > start_time else 0
            print(f"🚀 {db_name}: {len(missing_records):,} en {end_time - start_time:.1f}s ({rate:.0f} reg/s)")
        
        # Verificación final
        cluster_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        final_total = cluster_cursor.fetchone()[0]
        print(f"📊 {db_name}: FINAL - Local {local_total:,} vs Cluster {final_total:,}")
        
        return final_total >= local_total * 0.99
        
    except Exception as e:
        print(f"❌ {db_name}: Error: {e}")
        return False

def find_and_migrate_missing():
    """Respaldo dual completo"""
    print("=== RESPALDO DUAL COMPLETO ===")
    print("✅ TODAS las tablas core_ + InteractionDetail")
    print()
    
    try:
        # Conectar local (SOLO LECTURA)
        local_conn = psycopg2.connect(**LOCAL_DB)
        local_cursor = local_conn.cursor()
        
        local_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        local_total = local_cursor.fetchone()[0]
        print(f"✅ Local: {local_total:,} registros InteractionDetail")
        print()
        
        results = []
        
        # Respaldo primario
        print("🔄 RESPALDO PRIMARIO (telemetry_api)")
        conn1, cursor1, total1 = backup_to_database(CLUSTER_DB_PRIMARY, "telemetry_api")
        if conn1 and cursor1:
            result1 = sync_to_database(local_conn, local_cursor, conn1, cursor1, "telemetry_api", local_total)
            results.append(("telemetry_api", result1))
            cursor1.close()
            conn1.close()
        else:
            results.append(("telemetry_api", False))
        
        print()
        
        # Respaldo secundario
        print("🔄 RESPALDO SECUNDARIO (data_store_telemetry)")
        conn2, cursor2, total2 = backup_to_database(CLUSTER_DB_BACKUP, "data_store_telemetry")
        if conn2 and cursor2:
            result2 = sync_to_database(local_conn, local_cursor, conn2, cursor2, "data_store_telemetry", local_total)
            results.append(("data_store_telemetry", result2))
            cursor2.close()
            conn2.close()
        else:
            results.append(("data_store_telemetry", False))
        
        local_cursor.close()
        local_conn.close()
        
        # Resumen
        print()
        print("=== RESUMEN RESPALDO DUAL ===")
        success_count = sum(1 for _, result in results if result)
        
        for db_name, result in results:
            status = "✅ EXITOSO" if result else "❌ FALLÓ"
            print(f"📊 {db_name}: {status}")
        
        return success_count > 0
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def run():
    """Función para cron"""
    try:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando respaldo dual completo...")
        result = find_and_migrate_missing()
        status = "exitoso" if result else "falló"
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Respaldo dual completo {status}")
        return result
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error: {e}")
        return False

if __name__ == "__main__":
    find_and_migrate_missing()
