#!/usr/bin/env python3
"""
SCRIPT: SINCRONIZAR CLUSTER → LOCAL SEGURO
Descripción: Trae toda la data del cluster DigitalOcean a la DB local segura del VPS
Uso: python3 sync_cluster_to_local.py
"""

import os
import time
from datetime import datetime

import psycopg2
import psycopg2.extras


# Cargar variables de entorno
def load_env():
    """Cargar variables de entorno desde archivo .env"""
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

    if not os.path.exists(env_file):
        print(f"❌ Archivo .env no encontrado: {env_file}")
        print("💡 Crea .env con las variables necesarias")
        return False

    # Cargar variables
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

    return True


# CONFIGURACIÓN DE BASES DE DATOS
def get_db_config():
    """Obtener configuración de bases de datos desde variables de entorno"""
    CLUSTER_DB = {
        "host": os.environ.get("CLUSTER_DB_HOST"),
        "port": int(os.environ.get("CLUSTER_DB_PORT", 25060)),
        "user": os.environ.get("CLUSTER_DB_USER"),
        "password": os.environ.get("CLUSTER_DB_PASSWORD"),
        "database": os.environ.get("CLUSTER_DB_NAME"),
        "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
    }

    LOCAL_DB = {
        "host": os.environ.get("LOCAL_DB_HOST", "postgres"),
        "port": int(os.environ.get("LOCAL_DB_PORT", 5432)),
        "user": os.environ.get("LOCAL_DB_USER"),
        "password": os.environ.get("LOCAL_DB_PASSWORD"),
        "database": os.environ.get("LOCAL_DB_NAME"),
    }

    # Verificar que todas las variables estén definidas
    required_vars = {
        "CLUSTER_DB_HOST": CLUSTER_DB["host"],
        "CLUSTER_DB_USER": CLUSTER_DB["user"],
        "CLUSTER_DB_PASSWORD": CLUSTER_DB["password"],
        "CLUSTER_DB_NAME": CLUSTER_DB["database"],
        "LOCAL_DB_USER": LOCAL_DB["user"],
        "LOCAL_DB_PASSWORD": LOCAL_DB["password"],
        "LOCAL_DB_NAME": LOCAL_DB["database"],
    }

    missing_vars = [var for var, value in required_vars.items() if not value]

    if missing_vars:
        print(f"❌ Variables de entorno faltantes: {', '.join(missing_vars)}")
        return None, None

    return CLUSTER_DB, LOCAL_DB


def test_connections():
    """Probar conexiones a ambas bases de datos"""
    print("🔍 PROBANDO CONEXIONES...")

    CLUSTER_DB, LOCAL_DB = get_db_config()
    if not CLUSTER_DB or not LOCAL_DB:
        return False

    # Probar cluster
    try:
        cluster_conn = psycopg2.connect(**CLUSTER_DB)
        cluster_cursor = cluster_conn.cursor()
        cluster_cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"
        )
        cluster_tables = cluster_cursor.fetchone()[0]
        print(f"✅ CLUSTER: Conectado - {cluster_tables} tablas encontradas")
        cluster_cursor.close()
        cluster_conn.close()
    except Exception as e:
        print(f"❌ CLUSTER: Error de conexión - {e}")
        return False

    # Probar local
    try:
        local_conn = psycopg2.connect(**LOCAL_DB)
        local_cursor = local_conn.cursor()
        local_cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"
        )
        local_tables = local_cursor.fetchone()[0]
        print(f"✅ LOCAL: Conectado - {local_tables} tablas encontradas")
        local_cursor.close()
        local_conn.close()
    except Exception as e:
        print(f"❌ LOCAL: Error de conexión - {e}")
        return False

    return True


def get_table_info(cluster_cursor, table_name):
    """Obtener información de una tabla del cluster"""
    try:
        # Contar registros
        cluster_cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cluster_cursor.fetchone()[0]

        # Obtener estructura
        cluster_cursor.execute(
            f"""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' 
            ORDER BY ordinal_position;
            """
        )
        columns = cluster_cursor.fetchall()

        return count, columns
    except Exception as e:
        print(f"❌ Error obteniendo info de {table_name}: {e}")
        return 0, []


def sync_table(cluster_cursor, local_cursor, table_name, columns):
    """Sincronizar una tabla completa del cluster al local"""
    try:
        print(f"📊 Sincronizando {table_name}...")

        # 1. Obtener todos los datos del cluster
        cluster_cursor.execute(f"SELECT * FROM {table_name} ORDER BY id;")
        all_data = cluster_cursor.fetchall()

        if not all_data:
            print(f"   ⚠️  Tabla {table_name} está vacía")
            return True

        print(f"   📥 Obtenidos {len(all_data):,} registros del cluster")

        # 2. Limpiar tabla local
        local_cursor.execute(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;")
        print(f"   🗑️  Tabla local {table_name} limpiada")

        # 3. Preparar query de inserción (SIN ID para que se auto-genere)
        column_names = [col[0] for col in columns if col[0] != "id"]
        placeholders = ",".join(["%s"] * len(column_names))
        insert_query = f"INSERT INTO {table_name} ({','.join(column_names)}) VALUES ({placeholders})"

        # 4. Insertar en lotes para optimizar memoria
        batch_size = 1000
        total_inserted = 0

        start_time = time.time()

        for i in range(0, len(all_data), batch_size):
            batch = all_data[i : i + batch_size]

            # Preparar datos sin ID (excluir primera columna que es el ID)
            batch_data = [row[1:] for row in batch]

            # Insertar lote
            psycopg2.extras.execute_batch(
                local_cursor, insert_query, batch_data, page_size=batch_size
            )

            total_inserted += len(batch)
            print(
                f"   📤 Lote {i//batch_size + 1}: {len(batch):,} registros insertados"
            )

        # 5. Commit y verificación
        local_cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        final_count = local_cursor.fetchone()[0]

        sync_time = time.time() - start_time
        rate = total_inserted / sync_time if sync_time > 0 else 0

        print(
            f"   ✅ {table_name}: {final_count:,} registros sincronizados en {sync_time:.1f}s"
        )
        print(f"   🚀 Velocidad: {rate:.0f} reg/seg")
        print(f"   🔄 IDs regenerados automáticamente (sin conflictos)")

        return final_count == len(all_data)

    except Exception as e:
        print(f"   ❌ Error sincronizando {table_name}: {e}")
        return False


def reset_sequences(local_cursor, table_name):
    """Resetear secuencias de ID para la tabla"""
    try:
        # Obtener el máximo ID de la tabla
        local_cursor.execute(f"SELECT MAX(id) FROM {table_name};")
        max_id_result = local_cursor.fetchone()

        if max_id_result and max_id_result[0] is not None:
            max_id = max_id_result[0]

            # Resetear la secuencia al siguiente valor disponible
            local_cursor.execute(
                f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), {max_id + 1});"
            )
            print(f"   🔄 Secuencia de {table_name} reseteada a {max_id + 1}")
        else:
            # Si no hay datos, resetear a 1
            local_cursor.execute(
                f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), 1);"
            )
            print(f"   🔄 Secuencia de {table_name} reseteada a 1")

    except Exception as e:
        print(f"   ⚠️  No se pudo resetear secuencia de {table_name}: {e}")


def main_sync():
    """Función principal de sincronización"""
    print("🔄 SINCRONIZACIÓN CLUSTER → LOCAL SEGURA")
    print("=" * 50)
    print(f"⏰ Iniciado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. Cargar variables de entorno
    if not load_env():
        print("❌ No se pudieron cargar las variables de entorno")
        return False

    # 2. Probar conexiones
    if not test_connections():
        print("❌ No se pueden establecer conexiones. Abortando...")
        return False

    print()

    # 3. Obtener configuración de bases de datos
    CLUSTER_DB, LOCAL_DB = get_db_config()
    if not CLUSTER_DB or not LOCAL_DB:
        return False

    try:
        # 4. Conectar a ambas bases
        cluster_conn = psycopg2.connect(**CLUSTER_DB)
        cluster_cursor = cluster_conn.cursor()

        local_conn = psycopg2.connect(**LOCAL_DB)
        local_cursor = local_conn.cursor()

        # 5. Obtener lista de tablas del cluster
        print("📋 OBTENIENDO LISTA DE TABLAS...")
        cluster_cursor.execute(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """
        )
        tables = [row[0] for row in cluster_cursor.fetchall()]

        print(f"📊 Tablas encontradas en cluster: {len(tables)}")
        for table in tables:
            print(f"   - {table}")
        print()

        # 6. Sincronizar cada tabla
        print("🔄 INICIANDO SINCRONIZACIÓN...")
        print()

        success_count = 0
        total_records = 0

        for table_name in tables:
            try:
                # Obtener info de la tabla
                count, columns = get_table_info(cluster_cursor, table_name)

                if count > 0:
                    # Sincronizar tabla
                    if sync_table(cluster_cursor, local_cursor, table_name, columns):
                        # Resetear secuencia de ID
                        reset_sequences(local_cursor, table_name)
                        success_count += 1
                        total_records += count
                    else:
                        print(f"❌ Falló sincronización de {table_name}")
                else:
                    print(f"⚠️  Tabla {table_name} está vacía, saltando...")

                print()  # Separador entre tablas

            except Exception as e:
                print(f"❌ Error procesando tabla {table_name}: {e}")
                print()

        # 7. Verificación final
        print("🔍 VERIFICACIÓN FINAL...")
        print("=" * 50)

        # Verificar que todas las tablas tengan datos
        for table_name in tables:
            local_cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            local_count = local_cursor.fetchone()[0]

            cluster_cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            cluster_count = cluster_cursor.fetchone()[0]

            status = "✅" if local_count == cluster_count else "❌"
            print(f"{status} {table_name}: {local_count:,} / {cluster_count:,}")

        print()
        print(f"🎉 SINCRONIZACIÓN COMPLETADA:")
        print(f"   📊 Tablas exitosas: {success_count}/{len(tables)}")
        print(f"   📈 Total de registros: {total_records:,}")
        print(f"   🔄 IDs regenerados automáticamente")
        print(f"   ⏰ Tiempo total: {datetime.now().strftime('%H:%M:%S')}")

        # 8. Cerrar conexiones
        cluster_cursor.close()
        cluster_conn.close()
        local_cursor.close()
        local_conn.close()

        return True

    except Exception as e:
        print(f"❌ ERROR GENERAL: {e}")
        return False


if __name__ == "__main__":
    # Ejecutar sincronización
    success = main_sync()

    if success:
        print(
            "\n✅ SINCRONIZACIÓN EXITOSA - Tu DB local segura ahora tiene toda la data del cluster!"
        )
        print("🚀 La API ahora accederá a datos locales (más rápido)")
        print("🔒 Base de datos local NO expuesta públicamente")
        print("💾 El cluster seguirá siendo tu respaldo automático cada hora")
        print("🔄 IDs regenerados automáticamente (sin conflictos)")
    else:
        print("\n❌ SINCRONIZACIÓN FALLÓ - Revisa los errores arriba")

    print(f"\n⏰ Finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
