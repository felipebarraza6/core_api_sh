#!/usr/bin/env python3
"""
DELETE STAGING
Script simple para eliminar la tabla staging_interactiondetail
"""

import psycopg2
from datetime import datetime

# Configuración del cluster
CLUSTER_DB = {
    "host": "db-postgresql-nyc3-22918-do-user-7500906-0.m.db.ondigitalocean.com",
    "port": "25060",
    "user": "doadmin",
    "password": "AVNS_IofCPFJBY9PRQ1JQfpR",
    "database": "telemetry_api",
    "sslmode": "require",
}

def conectar_cluster():
    """Conectar al cluster DigitalOcean"""
    try:
        conn = psycopg2.connect(**CLUSTER_DB)
        print("✅ Conexión exitosa al cluster")
        return conn
    except Exception as e:
        print(f"❌ Error conectando: {e}")
        return None

def verificar_staging(conn):
    """Verificar si existe la tabla staging"""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_name = 'staging_interactiondetail'
        """)
        
        existe = cursor.fetchone()[0] > 0
        cursor.close()
        
        if existe:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM staging_interactiondetail")
            count = cursor.fetchone()[0]
            cursor.close()
            
            print(f"⚠️  Tabla staging encontrada:")
            print(f"   📊 Registros: {count:,}")
            return True, count
        else:
            print("✅ No hay tabla staging")
            return False, 0
            
    except Exception as e:
        print(f"❌ Error verificando staging: {e}")
        return False, 0

def eliminar_staging(conn):
    """Eliminar la tabla staging"""
    try:
        print("\n🗑️  ELIMINANDO TABLA STAGING...")
        
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS staging_interactiondetail CASCADE")
        conn.commit()
        cursor.close()
        
        print("✅ Tabla staging_interactiondetail ELIMINADA")
        return True
        
    except Exception as e:
        print(f"❌ Error eliminando tabla: {e}")
        conn.rollback()
        return False

def verificar_eliminacion(conn):
    """Verificar que la tabla fue eliminada"""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_name = 'staging_interactiondetail'
        """)
        
        existe = cursor.fetchone()[0] > 0
        cursor.close()
        
        if not existe:
            print("✅ Verificación exitosa: Tabla eliminada")
            return True
        else:
            print("❌ Error: Tabla aún existe")
            return False
            
    except Exception as e:
        print(f"❌ Error verificando eliminación: {e}")
        return False

def crear_log(registros_eliminados):
    """Crear archivo de log"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"staging_deleted_{timestamp}.log"
    
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write("ELIMINACIÓN DE TABLA STAGING\n")
        f.write("=" * 30 + "\n")
        f.write(f"Fecha: {datetime.now()}\n")
        f.write(f"Tabla: staging_interactiondetail\n")
        f.write(f"Registros: {registros_eliminados:,}\n")
        f.write(f"Estado: ELIMINADA\n")
    
    print(f"📝 Log creado: {log_file}")

def main():
    """Función principal"""
    print("🗑️  ELIMINAR TABLA STAGING DEL CLUSTER")
    print("=" * 50)
    
    # Conectar
    conn = conectar_cluster()
    if not conn:
        return
    
    try:
        # Verificar staging
        existe, registros = verificar_staging(conn)
        if not existe:
            return
        
        # Confirmar eliminación
        print(f"\n⚠️  CONFIRMACIÓN REQUERIDA:")
        print(f"   Se va a eliminar la tabla staging_interactiondetail")
        print(f"   Registros: {registros:,}")
        print(f"   Esta acción NO SE PUEDE DESHACER")
        
        confirmacion = input("\n¿Continuar? (escribe 'SI' para confirmar): ")
        if confirmacion.upper() != 'SI':
            print("❌ Eliminación cancelada")
            return
        
        # Eliminar
        if eliminar_staging(conn):
            # Verificar
            if verificar_eliminacion(conn):
                # Crear log
                crear_log(registros)
                
                print(f"\n🎉 ELIMINACIÓN COMPLETADA:")
                print(f"   📊 Registros eliminados: {registros:,}")
                print(f"   📝 Log de eliminación creado")
            else:
                print("❌ Error en verificación")
        else:
            print("❌ Error eliminando tabla")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
