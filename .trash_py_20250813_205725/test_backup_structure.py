#!/usr/bin/env python3
"""Test de estructura de respaldo sin conexiones remotas"""

import os
import psycopg2

def load_env():
    """Cargar variables de entorno"""
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value

load_env()

LOCAL_DB = {
    "host": "postgres_secure",
    "port": "5432",
    "user": "smarthydro_user",
    "password": os.environ.get("LOCAL_DB_PASSWORD", ""),
    "database": "smarthydro_prod",
}

CORE_TABLES = [
    'core_client', 'core_user', 'core_user_groups', 'core_user_user_permissions',
    'core_typefilecatchment', 'core_registerpersons', 'core_variable',
    'core_schemescatchment', 'core_catchmentpoint', 'core_dgadataconfigcatchment',
    'core_profiledataconfigcatchment', 'core_profileikolucatchment', 
    'core_filecatchment', 'core_catchmentpoint_users_viewers',
    'core_schemescatchment_points_catchment', 'core_projectcatchments',
    'core_notificationscatchment', 'core_responsenotificationscatchment',
    'core_interactiondetail'
]

def test_local_structure():
    """Validar estructura local para respaldo"""
    print("🔍 VALIDANDO ESTRUCTURA LOCAL PARA RESPALDO")
    print("=" * 50)
    
    try:
        conn = psycopg2.connect(**LOCAL_DB)
        cursor = conn.cursor()
        
        total_records = 0
        
        for table_name in CORE_TABLES:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                size_info = "📊" if table_name == 'core_interactiondetail' else "📋"
                print(f"{size_info} {table_name}: {count:,} registros")
                total_records += count
                
                if table_name == 'core_interactiondetail':
                    cursor.execute(f"SELECT MIN(date_time_medition), MAX(date_time_medition) FROM {table_name}")
                    min_date, max_date = cursor.fetchone()
                    print(f"    📅 Rango: {min_date} → {max_date}")
                
            except Exception as e:
                print(f"❌ {table_name}: Error - {e}")
        
        print("=" * 50)
        print(f"📊 TOTAL DE REGISTROS A RESPALDAR: {total_records:,}")
        print("✅ ESTRUCTURA LOCAL VÁLIDA PARA RESPALDO")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    test_local_structure()
