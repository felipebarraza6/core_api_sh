#!/usr/bin/env python3
"""
BACKUP CLUSTER
Script simple para hacer backup completo del cluster DigitalOcean
"""

import psycopg2
import os
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

def obtener_tablas(conn):
    """Obtener lista de tablas del cluster"""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        
        tablas = [row[0] for row in cursor.fetchall()]
        cursor.close()
        
        print(f"📊 Tablas encontradas: {len(tablas)}")
        return tablas
    except Exception as e:
        print(f"❌ Error obteniendo tablas: {e}")
        return []

def crear_directorio_backup():
    """Crear directorio para el backup"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backup_cluster_{timestamp}"
    
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        print(f"📁 Directorio creado: {backup_dir}")
    
    return backup_dir

def respaldar_tabla(conn, tabla, backup_dir):
    """Respaldar una tabla específica"""
    try:
        # Estructura de la tabla
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {tabla} LIMIT 0")
        cursor.close()
        
        # Crear archivo SQL
        archivo_sql = os.path.join(backup_dir, f"{tabla}_backup.sql")
        
        with open(archivo_sql, 'w', encoding='utf-8') as f:
            f.write(f"-- Backup de tabla: {tabla}\n")
            f.write(f"-- Fecha: {datetime.now()}\n\n")
            
            # CREATE TABLE
            cursor = conn.cursor()
            cursor.execute(f"SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name = '{tabla}' ORDER BY ordinal_position")
            columnas_info = cursor.fetchall()
            
            f.write(f"CREATE TABLE IF NOT EXISTS {tabla} (\n")
            for i, (col, tipo, nullable, default) in enumerate(columnas_info):
                null_text = "NULL" if nullable == "YES" else "NOT NULL"
                default_text = f" DEFAULT {default}" if default else ""
                f.write(f"    {col} {tipo}{default_text} {null_text}")
                if i < len(columnas_info) - 1:
                    f.write(",")
                f.write("\n")
            f.write(");\n\n")
            
            # INSERT DATA
            cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
            total_registros = cursor.fetchone()[0]
            
            if total_registros > 0:
                f.write(f"-- Insertando {total_registros:,} registros\n")
                f.write(f"COPY {tabla} FROM STDIN;\n")
                
                # Copiar datos en chunks para evitar memoria
                chunk_size = 1000
                offset = 0
                
                while offset < total_registros:
                    cursor.execute(f"SELECT * FROM {tabla} LIMIT {chunk_size} OFFSET {offset}")
                    registros = cursor.fetchall()
                    
                    for registro in registros:
                        valores = []
                        for valor in registro:
                            if valor is None:
                                valores.append("\\N")
                            elif isinstance(valor, str):
                                valores.append(valor.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n"))
                            else:
                                valores.append(str(valor))
                        f.write("\t".join(valores) + "\n")
                    
                    offset += chunk_size
                
                f.write("\\.\n")
            
            cursor.close()
        
        print(f"   ✅ {tabla}: {total_registros:,} registros")
        return True
        
    except Exception as e:
        print(f"   ❌ Error respaldando {tabla}: {e}")
        return False

def crear_resumen_backup(backup_dir, tablas_respaldadas):
    """Crear archivo de resumen del backup"""
    archivo_resumen = os.path.join(backup_dir, "RESUMEN_BACKUP.md")
    
    with open(archivo_resumen, 'w', encoding='utf-8') as f:
        f.write("# 📦 RESUMEN DE BACKUP DEL CLUSTER\n\n")
        f.write(f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Directorio:** {backup_dir}\n\n")
        
        f.write("## 📋 TABLAS RESPALDADAS\n\n")
        for tabla in tablas_respaldadas:
            f.write(f"- {tabla}\n")
        
        f.write(f"\n## 🎯 TOTAL\n\n")
        f.write(f"- **Tablas respaldadas:** {len(tablas_respaldadas)}\n")
        f.write(f"- **Archivos generados:** {len(tablas_respaldadas) + 1}\n")
        
        f.write(f"\n## 📁 ARCHIVOS\n\n")
        f.write(f"- `RESUMEN_BACKUP.md` - Este archivo\n")
        for tabla in tablas_respaldadas:
            f.write(f"- `{tabla}_backup.sql` - Backup de {tabla}\n")
    
    print(f"📝 Resumen creado: {archivo_resumen}")

def main():
    """Función principal"""
    print("📦 BACKUP COMPLETO DEL CLUSTER DIGITALOCEAN")
    print("=" * 50)
    
    # Conectar
    conn = conectar_cluster()
    if not conn:
        return
    
    try:
        # Obtener tablas
        tablas = obtener_tablas(conn)
        if not tablas:
            return
        
        # Crear directorio
        backup_dir = crear_directorio_backup()
        
        # Respaldar cada tabla
        print(f"\n🔄 RESPALDANDO TABLAS...")
        tablas_respaldadas = []
        
        for tabla in tablas:
            if respaldar_tabla(conn, tabla, backup_dir):
                tablas_respaldadas.append(tabla)
        
        # Crear resumen
        crear_resumen_backup(backup_dir, tablas_respaldadas)
        
        print(f"\n🎉 BACKUP COMPLETADO:")
        print(f"   📁 Directorio: {backup_dir}")
        print(f"   📊 Tablas: {len(tablas_respaldadas)}/{len(tablas)}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
