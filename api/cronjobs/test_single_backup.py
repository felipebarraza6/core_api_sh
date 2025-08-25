#!/usr/bin/env python3
"""Test de respaldo a UNA sola base para validar funcionamiento"""

import os
import time
import psycopg2
import psycopg2.extras

CORE_OPERATIONAL_TABLES = [
    'core_client', 'core_user', 'core_user_groups', 'core_user_user_permissions',
    'core_typefilecatchment', 'core_registerpersons', 'core_variable',
    'core_schemescatchment', 'core_catchmentpoint', 'core_dgadataconfigcatchment',
    'core_profiledataconfigcatchment', 'core_profileikolucatchment', 
    'core_filecatchment', 'core_catchmentpoint_users_viewers',
    'core_schemescatchment_points_catchment', 'core_projectcatchments',
    'core_notificationscatchment', 'core_responsenotificationscatchment'
]

def load_env():
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
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

# SOLO UNA BASE PARA TEST
TEST_DB = {
    "host": os.environ.get("CLUSTER_DB_HOST", "db-postgresql.com"),
    "port": os.environ.get("CLUSTER_DB_PORT", "123"),
    "user": os.environ.get("CLUSTER_DB_USER", "admin"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD", ""),
    "database": os.environ.get("CLUSTER_DB_NAME", "telemetry_api"),
    "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
}

def test_single_connection():
    """Test de conexión a una sola base"""
    print("🧪 TEST DE CONEXIÓN ÚNICA")
    print("=" * 40)
    
    try:
        # Conectar LOCAL
        print("🔌 Conectando a base LOCAL...")
        local_conn = psycopg2.connect(**LOCAL_DB)
        local_cursor = local_conn.cursor()
        
        local_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail")
        local_total = local_cursor.fetchone()[0]
        print(f"✅ LOCAL: {local_total:,} registros")
        
        # Conectar REMOTA (solo una)
        print("🔌 Conectando a base REMOTA (telemetry_api)...")
        
        # Timeout corto para evitar cuelgues
        import socket
        socket.setdefaulttimeout(10)  # 10 segundos máximo
        
        remote_conn = psycopg2.connect(**TEST_DB)
        remote_cursor = remote_conn.cursor()
        
        try:
            remote_cursor.execute("SELECT COUNT(*) FROM core_interactiondetail")
            remote_total = remote_cursor.fetchone()[0]
            print(f"✅ REMOTA: {remote_total:,} registros")
            
            # Test simple: contar diferencia
            difference = local_total - remote_total
            print(f"📊 DIFERENCIA: {difference:,} registros")
            
            if difference > 0:
                print(f"🔄 Se necesitarían migrar ~{difference:,} registros")
            else:
                print("✅ Bases sincronizadas")
                
        except Exception as e:
            print(f"⚠️ InteractionDetail no existe en remota: {e}")
            print("🔧 Sería primera sincronización completa")
        
        # Cerrar conexiones
        remote_cursor.close()
        remote_conn.close()
        local_cursor.close()
        local_conn.close()
        
        print("✅ TEST DE CONEXIÓN EXITOSO")
        return True
        
    except socket.timeout:
        print("❌ TIMEOUT: Conexión remota muy lenta")
        return False
    except Exception as e:
        print(f"❌ ERROR DE CONEXIÓN: {e}")
        return False

def test_small_operation():
    """Test de operación pequeña (solo contar tablas operativas)"""
    print()
    print("🧪 TEST DE OPERACIÓN PEQUEÑA")
    print("=" * 40)
    
    try:
        local_conn = psycopg2.connect(**LOCAL_DB)
        local_cursor = local_conn.cursor()
        
        print("📋 Contando tablas operativas locales:")
        operational_total = 0
        
        for table in CORE_OPERATIONAL_TABLES[:5]:  # Solo las primeras 5
            try:
                local_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = local_cursor.fetchone()[0]
                print(f"   {table}: {count}")
                operational_total += count
            except:
                print(f"   {table}: No existe")
        
        print(f"📊 TOTAL OPERATIVAS (muestra): {operational_total}")
        
        local_cursor.close()
        local_conn.close()
        
        print("✅ TEST DE OPERACIÓN EXITOSO")
        return True
        
    except Exception as e:
        print(f"❌ ERROR EN OPERACIÓN: {e}")
        return False

def run_single_test():
    """Ejecutar test único de validación"""
    print("🚀 INICIANDO TEST DE RESPALDO ÚNICO")
    print("=" * 50)
    
    start_time = time.time()
    
    # Test 1: Conexiones
    if not test_single_connection():
        print("❌ FALLO EN CONEXIONES")
        return False
    
    # Test 2: Operación pequeña
    if not test_small_operation():
        print("❌ FALLO EN OPERACIÓN")
        return False
    
    end_time = time.time()
    duration = end_time - start_time
    
    print("=" * 50)
    print(f"🎉 TESTS COMPLETADOS EN {duration:.1f}s")
    print("✅ SISTEMA LISTO PARA RESPALDO REAL")
    
    return True

if __name__ == "__main__":
    run_single_test()
