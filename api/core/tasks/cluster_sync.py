"""
Celery Task for Cluster Data Synchronization (Dual Backup)
Replaces cronjobs/cluster_backup_complete_final.py
"""

import logging
import os
import time
import psycopg2
import psycopg2.extras
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

# Operational tables to sync to telemetry_api DB
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

@shared_task(bind=True, max_retries=2)
def run_cluster_sync(self):
    """
    Execute dual-database synchronization
    Syncs operational data to 'telemetry_api' and measurements to 'data_store_telemetry'
    """
    start_time = time.time()
    logger.info("Starting cluster synchronization")
    
    results = {
        'config_sync': False,
        'telemetry_sync': False,
        'errors': []
    }

    try:
        # Get connection params
        local_db = settings.DATABASES['default'].copy()
        
        # Get cluster configs from env
        cluster_host = os.environ.get("CLUSTER_DB_HOST")
        cluster_port = os.environ.get("CLUSTER_DB_PORT", "25060")
        cluster_ssl = os.environ.get("CLUSTER_DB_SSLMODE", "require")
        
        if not cluster_host:
            logger.warning("CLUSTER_DB_HOST not set, skipping sync")
            return {'status': 'skipped', 'reason': 'No cluster config'}

        # Connect to local DB
        local_conn = psycopg2.connect(
            host=local_db['HOST'],
            port=local_db['PORT'],
            user=local_db['USER'],
            password=local_db['PASSWORD'],
            dbname=local_db['NAME']
        )
        local_cursor = local_conn.cursor()

        # 1. Sync Config (telemetry_api)
        try:
            config_conn = psycopg2.connect(
                host=cluster_host,
                port=cluster_port,
                user=os.environ.get("CLUSTER_DB_USER", "api_principal"),
                password=os.environ.get("CLUSTER_DB_PASSWORD", ""),
                dbname=os.environ.get("CLUSTER_DB_NAME", "telemetry_api"),
                sslmode=cluster_ssl
            )
            config_cursor = config_conn.cursor()
            
            sync_count = sync_operational_tables(local_cursor, config_conn, config_cursor)
            results['config_sync'] = True
            results['tables_synced'] = sync_count
            
            config_cursor.close()
            config_conn.close()
            
        except Exception as exc:
            logger.error(f"Config sync failed: {exc}")
            results['errors'].append(f"Config sync: {exc}")

        # 2. Sync Telemetry (data_store_telemetry)
        try:
            telemetry_conn = psycopg2.connect(
                host=cluster_host,
                port=cluster_port,
                user=os.environ.get("CLUSTER_DB_USER_BACKUP", "api_principal"),
                password=os.environ.get("CLUSTER_DB_PASSWORD_BACKUP", ""),
                dbname="data_store_telemetry",
                sslmode=cluster_ssl
            )
            telemetry_cursor = telemetry_conn.cursor()
            
            records_synced = sync_telemetry_data(local_cursor, telemetry_conn, telemetry_cursor)
            results['telemetry_sync'] = True
            results['records_synced'] = records_synced
            
            telemetry_cursor.close()
            telemetry_conn.close()
            
        except Exception as exc:
            logger.error(f"Telemetry sync failed: {exc}")
            results['errors'].append(f"Telemetry sync: {exc}")

        local_cursor.close()
        local_conn.close()

        execution_time = time.time() - start_time
        logger.info(f"Cluster sync completed in {execution_time:.2f}s")
        results['execution_time'] = execution_time
        
        return results

    except Exception as exc:
        logger.error(f"Cluster sync critical error: {exc}")
        self.retry(countdown=3600, exc=exc)


def sync_operational_tables(local_cursor, cluster_conn, cluster_cursor):
    """Sync operational tables logic"""
    synced_count = 0
    
    for table in OPERATIONAL_TABLES:
        try:
            # Basic sync logic adapted from original script
            # 1. Check if table exists in local
            local_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            local_count = local_cursor.fetchone()[0]
            if local_count == 0:
                continue

            # 2. Get columns
            local_cursor.execute(f"SELECT * FROM {table} LIMIT 0")
            columns = [desc[0] for desc in local_cursor.description]
            
            # 3. Get max ID in cluster
            try:
                cluster_cursor.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
                max_id = cluster_cursor.fetchone()[0]
            except:
                max_id = 0
            
            # 4. Fetch new rows
            local_cursor.execute(f"SELECT * FROM {table} WHERE id > %s ORDER BY id", (max_id,))
            rows = local_cursor.fetchall()
            
            if not rows:
                synced_count += 1
                continue
                
            # 5. Insert
            cols_str = ",".join(columns)
            vals_str = ",".join(["%s"] * len(columns))
            
            # Construct ON CONFLICT update
            updates = [f"{c}=EXCLUDED.{c}" for c in columns if c != 'id']
            update_clause = f"ON CONFLICT (id) DO UPDATE SET {','.join(updates)}" if updates else "ON CONFLICT (id) DO NOTHING"
            
            query = f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str}) {update_clause}"
            
            psycopg2.extras.execute_values(cluster_cursor, query, rows)
            cluster_conn.commit()
            synced_count += 1
            
        except Exception as exc:
            logger.warning(f"Failed to sync table {table}: {exc}")
            cluster_conn.rollback()
            
    return synced_count


def sync_telemetry_data(local_cursor, cluster_conn, cluster_cursor):
    """Sync TelemetryRecord data"""
    # Check max ID in cluster
    try:
        cluster_cursor.execute("SELECT COALESCE(MAX(id), 0) FROM core_telemetryrecordv3")
        max_id = cluster_cursor.fetchone()[0]
    except:
        max_id = 0
        
    # Fetch new records from local
    local_cursor.execute("""
        SELECT id, created, modified, timestamp,
               data, metadata,
               send_dga, return_dga, n_voucher, is_error, point_id,
               is_partial
        FROM core_telemetryrecordv3
        WHERE id > %s
        ORDER BY id
        LIMIT 50000
    """, (max_id,))
    
    rows = local_cursor.fetchall()
    if not rows:
        return 0
        
    # Insert into cluster
    insert_query = """
        INSERT INTO core_telemetryrecordv3 
        (id, created, modified, timestamp,
         data, metadata,
         send_dga, return_dga, n_voucher, is_error, point_id,
         is_partial)
        VALUES %s
        ON CONFLICT (id) DO NOTHING
    """
    
    psycopg2.extras.execute_values(cluster_cursor, insert_query, rows, page_size=1000)
    cluster_conn.commit()
    
    return len(rows)
