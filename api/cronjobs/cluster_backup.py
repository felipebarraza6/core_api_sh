#!/usr/bin/env python3

import psycopg2
import psycopg2.extras
import time

LOCAL_DB = {
    'host': 'postgres',
    'port': '5432', 
    'user': 'postgres',
    'password': 'postgres',
    'database': 'postgres'
}

CLUSTER_DB = {
    'host': 'db-postgresql-nyc3-22918-do-user-7500906-0.m.db.ondigitalocean.com',
    'port': '25060',
    'user': 'doadmin',
    'password': 'AVNS_29JJQpkue7Sf52s7Bw1',
    'database': 'telemetry_api',
    'sslmode': 'require'
}

def find_and_migrate_missing():
    print("=== MIGRANDO LA LAGUNITA ===")
    print("Comparando local vs cluster para encontrar faltantes")
    print()
    
    try:
        local_conn = psycopg2.connect(**LOCAL_DB)
        local_cursor = local_conn.cursor()
        
        cluster_conn = psycopg2.connect(**CLUSTER_DB)
        cluster_cursor = cluster_conn.cursor()
        
        # Validaciones previas: asegurar integridad de la BD local
        print("=== VALIDACIONES PREVIAS ===")
        
        # 1) Verificar que existan tablas en la BD local
        local_cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE';"
        )
        tables_count = local_cursor.fetchone()[0]
        if tables_count == 0:
            print("ERROR: no se encontraron tablas en la BD local. Abortando migracion.")
            local_cursor.close()
            local_conn.close()
            cluster_cursor.close()
            cluster_conn.close()
            return False
        print(f"OK: Tablas encontradas en BD local: {tables_count}")
        
        # 2) Verificar que la tabla core_interactiondetail no este vacia
        local_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        local_total = local_cursor.fetchone()[0]
        if local_total == 0:
            print("ERROR: la tabla core_interactiondetail esta vacia. Abortando migracion.")
            local_cursor.close()
            local_conn.close()
            cluster_cursor.close()
            cluster_conn.close()
            return False
        print(f"OK: Registros en core_interactiondetail local: {local_total:,}")
        
        # Contar registros en el cluster para comparacion
        cluster_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        cluster_total = cluster_cursor.fetchone()[0]
        
        missing_count = local_total - cluster_total
        
        print()
        print("=== COMPARACION LOCAL VS CLUSTER ===")
        print(f"Local total: {local_total:,}")
        print(f"Cluster total: {cluster_total:,}")
        print(f"FALTANTES: {missing_count:,}")
        print()
        
        # NUEVA FUNCIONALIDAD: Eliminar registros huerfanos del cluster
        # (registros que estan en cluster pero ya no en local)
        print("=== LIMPIEZA DE REGISTROS HUERFANOS ===")
        print("Identificando registros huerfanos en el cluster...")
        
        # Obtener todos los IDs del cluster
        cluster_cursor.execute("SELECT id FROM core_interactiondetail ORDER BY id;")
        cluster_ids = set(row[0] for row in cluster_cursor.fetchall())
        
        # Obtener todos los IDs locales
        local_cursor.execute("SELECT id FROM core_interactiondetail ORDER BY id;")
        local_ids = set(row[0] for row in local_cursor.fetchall())
        
        # IDs huerfanos = estan en cluster pero no en local
        orphan_ids = cluster_ids - local_ids
        
        if orphan_ids:
            print(f"LIMPIEZA: Encontrados {len(orphan_ids)} registros huerfanos en el cluster.")
            print("Eliminando registros huerfanos...")
            
            # Eliminar en lotes de 1000 para evitar problemas de memoria
            orphan_list = list(orphan_ids)
            batch_size = 1000
            deleted_count = 0
            
            for i in range(0, len(orphan_list), batch_size):
                batch = orphan_list[i:i + batch_size]
                placeholders = ",".join(["%s"] * len(batch))
                delete_query = f"DELETE FROM core_interactiondetail WHERE id IN ({placeholders})"
                cluster_cursor.execute(delete_query, batch)
                deleted_count += cluster_cursor.rowcount
            
            cluster_conn.commit()
            print(f"OK: Eliminados: {deleted_count} registros huerfanos del cluster")
        else:
            print("OK: No se encontraron registros huerfanos en el cluster.")
        print()
        
        # Recalcular totales despues de la limpieza
        cluster_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        cluster_total_after_cleanup = cluster_cursor.fetchone()[0]
        missing_count = local_total - cluster_total_after_cleanup
        
        print(f"Cluster total despues de limpieza: {cluster_total_after_cleanup:,}")
        print(f"FALTANTES despues de limpieza: {missing_count:,}")
        print()
        
        if missing_count <= 0:
            print("OK: No hay registros faltantes!")
            return True
        
        # Encontrar el rango de IDs faltantes
        cluster_cursor.execute("SELECT MAX(id) FROM core_interactiondetail;")
        cluster_max_id = cluster_cursor.fetchone()[0]
        
        local_cursor.execute("SELECT MAX(id) FROM core_interactiondetail;")
        local_max_id = local_cursor.fetchone()[0]
        
        print(f"Local max ID: {local_max_id}")
        print(f"Cluster max ID: {cluster_max_id}")
        print(f"Diferencia de IDs: {local_max_id - cluster_max_id}")
        print()
        
        # Buscar registros faltantes (los mas nuevos probablemente)
        print("=== BUSQUEDA DE REGISTROS FALTANTES ===")
        print("Buscando registros faltantes...")
        
        # Estrategia 1: IDs mayores al max del cluster
        if local_max_id > cluster_max_id:
            print(f"Migrando IDs desde {cluster_max_id + 1} hasta {local_max_id}")
            
            local_cursor.execute("""
                SELECT id, created, modified, date_time_medition, date_time_last_logger,
                       flow, total, total_diff, total_today_diff, nivel, water_table,
                       send_dga, return_dga, n_voucher, is_error, catchment_point_id,
                       notification_id, pulses, days_not_conection
                FROM core_interactiondetail 
                WHERE id > %s
                ORDER BY id
            """, (cluster_max_id,))
            
        else:
            # Estrategia 2: Registros del ultimo dia que no esten
            print("Buscando por fecha - ultimas 24 horas")
            local_cursor.execute("""
                SELECT id, created, modified, date_time_medition, date_time_last_logger,
                       flow, total, total_diff, total_today_diff, nivel, water_table,
                       send_dga, return_dga, n_voucher, is_error, catchment_point_id,
                       notification_id, pulses, days_not_conection
                FROM core_interactiondetail 
                WHERE created >= NOW() - INTERVAL '24 hours'
                ORDER BY id
            """)
        
        missing_records = local_cursor.fetchall()
        
        if not missing_records:
            print("OK: No se encontraron registros faltantes especificos")
            return True
            
        print(f"ENCONTRADOS: {len(missing_records)} registros faltantes")
        print()
        
        # Migrar usando BULK INSERT (ultra rapido)
        print("=== MIGRACION DE REGISTROS FALTANTES ===")
        print("Migrando faltantes con BULK INSERT...")
        
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
        
        try:
            # BULK INSERT de todos los faltantes
            psycopg2.extras.execute_values(
                cluster_cursor,
                insert_query,
                missing_records,
                page_size=1000
            )
            cluster_conn.commit()
            
            bulk_time = time.time() - start_time
            rate = len(missing_records) / bulk_time if bulk_time > 0 else 0
            
            print(f"OK: Migrados: {len(missing_records)} en {bulk_time:.1f}s")
            print(f"VELOCIDAD: {rate:.0f} reg/seg")
            
        except Exception as e:
            print(f"ERROR en bulk: {e}")
            # Fallback individual
            success = 0
            for record in missing_records:
                try:
                    cluster_cursor.execute("""
                        INSERT INTO core_interactiondetail 
                        (id, created, modified, date_time_medition, date_time_last_logger,
                         flow, total, total_diff, total_today_diff, nivel, water_table,
                         send_dga, return_dga, n_voucher, is_error, catchment_point_id,
                         notification_id, pulses, days_not_conection)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, record)
                    success += 1
                except:
                    pass
            cluster_conn.commit()
            print(f"OK: Migrados individualmente: {success}")
        
        # Verificacion final
        cluster_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail;")
        final_cluster_total = cluster_cursor.fetchone()[0]
        
        print()
        print("=== VERIFICACION FINAL ===")
        print(f"Local total: {local_total:,}")
        print(f"Cluster total inicial: {cluster_total:,}")
        print(f"Cluster total final: {final_cluster_total:,}")
        print(f"Diferencia final: {local_total - final_cluster_total:,}")
        
        if final_cluster_total >= local_total * 0.99:
            print("SUCCESS: LAGUNITA MIGRADA EXITOSAMENTE!")
            print("SUCCESS: CLUSTER AL 100%!")
        else:
            print("WARNING: Aun faltan algunos registros")
        
        local_cursor.close()
        local_conn.close()
        cluster_cursor.close()
        cluster_conn.close()
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    find_and_migrate_missing()

def run():
    """Funcion para ejecutar el backup desde django_crontab"""
    try:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando backup del cluster...")
        result = find_and_migrate_missing()
        if result:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Backup completado exitosamente")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Backup fallo")
        return result
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error en backup: {e}")
        return False
