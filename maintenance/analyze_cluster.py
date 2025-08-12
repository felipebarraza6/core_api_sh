#!/usr/bin/env python3
"""
ANALIZAR CLUSTER
Script simple para analizar el estado del cluster DigitalOcean
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


def analizar_tablas(conn):
    """Analizar tablas del cluster"""
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT table_name, column_count
            FROM (
                SELECT 
                    t.table_name,
                    COUNT(c.column_name) as column_count
                FROM information_schema.tables t
                LEFT JOIN information_schema.columns c 
                    ON t.table_name = c.table_name
                WHERE t.table_schema = 'public'
                GROUP BY t.table_name
            ) sub
            ORDER BY table_name
        """
        )

        tablas = cursor.fetchall()
        cursor.close()

        print(f"\n📊 TABLAS ENCONTRADAS: {len(tablas)}")
        print("-" * 40)
        for tabla, columnas in tablas:
            print(f"   📋 {tabla} ({columnas} columnas)")

        return tablas
    except Exception as e:
        print(f"❌ Error analizando tablas: {e}")
        return []


def contar_registros(conn):
    """Contar total de registros en el cluster"""
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT SUM(reltuples)::bigint
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
        """
        )

        total = cursor.fetchone()[0] or 0
        cursor.close()

        print(f"\n🎯 TOTAL DE REGISTROS: {total:,}")
        return total
    except Exception as e:
        print(f"❌ Error contando registros: {e}")
        return 0


def analizar_staging(conn):
    """Analizar tabla staging si existe"""
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_name = 'staging_interactiondetail'
        """
        )

        existe = cursor.fetchone()[0] > 0
        cursor.close()

        if existe:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM staging_interactiondetail")
            count = cursor.fetchone()[0]
            cursor.close()

            print(f"\n⚠️  TABLA STAGING ENCONTRADA:")
            print(f"   📊 Registros: {count:,}")
            print(f"   🗑️  Recomendación: Eliminar si está vacía")
        else:
            print(f"\n✅ No hay tabla staging")

        return existe
    except Exception as e:
        print(f"❌ Error analizando staging: {e}")
        return False


def main():
    """Función principal"""
    print("🔍 ANÁLISIS DEL CLUSTER DIGITALOCEAN")
    print("=" * 50)

    # Conectar
    conn = conectar_cluster()
    if not conn:
        return

    try:
        # Analizar
        analizar_tablas(conn)
        contar_registros(conn)
        analizar_staging(conn)

        print(f"\n✅ Análisis completado - {datetime.now().strftime('%H:%M:%S')}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
