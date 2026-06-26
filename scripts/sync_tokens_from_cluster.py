#!/usr/bin/env python3
"""
Script para sincronizar tokens desde cluster (correcto) a local.

El cluster es la fuente de verdad.
"""

import os
import sys
import psycopg2
import psycopg2.extras

# Cargar variables de entorno
sys.path.insert(0, '/root/core_api_sh')

def load_env():
    """Cargar .env"""
    # Intentar múltiples ubicaciones
    env_files = ['/app/.env', '/root/core_api_sh/.env', '.env']

    for env_file in env_files:
        if os.path.exists(env_file):
            print(f"📁 Cargando variables desde: {env_file}")
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key] = value
            return

    print("⚠️  No se encontró archivo .env")

load_env()

# Configuración cluster (FUENTE DE VERDAD)
CLUSTER_DB = {
    "host": os.environ.get("CLUSTER_DB_HOST"),
    "port": os.environ.get("CLUSTER_DB_PORT", "25060"),
    "user": os.environ.get("CLUSTER_DB_USER", "api_principal"),
    "password": os.environ.get("CLUSTER_DB_PASSWORD", ""),
    "database": os.environ.get("CLUSTER_DB_NAME", "telemetry_api"),
    "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
}

# Configuración local
LOCAL_DB = {
    "host": os.environ.get("LOCAL_DB_HOST", "postgres"),
    "port": os.environ.get("LOCAL_DB_PORT", "5432"),
    "user": os.environ.get("LOCAL_DB_USER", "smarthydro_user"),
    "password": os.environ.get("LOCAL_DB_PASSWORD", ""),
    "database": os.environ.get("LOCAL_DB_NAME", "smarthydro_prod"),
}

def main():
    print("\n" + "="*80)
    print("SINCRONIZACIÓN DE TOKENS: CLUSTER → LOCAL")
    print("="*80)

    # Conectar a cluster
    print("\n🔗 Conectando al CLUSTER (fuente de verdad)...")
    cluster_conn = psycopg2.connect(**CLUSTER_DB)
    cluster_cursor = cluster_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    print("✅ Conectado al cluster")

    # Conectar a local
    print("🔗 Conectando a base de datos LOCAL...")
    local_conn = psycopg2.connect(**LOCAL_DB)
    local_cursor = local_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    print("✅ Conectado a local")

    # Obtener todos los tokens del cluster
    print("\n📊 Obteniendo configuraciones del CLUSTER...")
    cluster_cursor.execute("""
        SELECT
            pdc.point_catchment_id,
            pdc.token_service,
            pdc.d1, pdc.d2, pdc.d3, pdc.d4, pdc.d5, pdc.d6,
            pdc.is_telemetry,
            cp.title
        FROM core_profiledataconfigcatchment pdc
        JOIN core_catchmentpoint cp ON cp.id = pdc.point_catchment_id
        ORDER BY pdc.point_catchment_id
    """)
    cluster_configs = cluster_cursor.fetchall()
    print(f"   Encontradas {len(cluster_configs)} configuraciones en cluster")

    # Obtener configuraciones locales
    print("📊 Obteniendo configuraciones LOCALES...")
    local_cursor.execute("""
        SELECT
            pdc.point_catchment_id,
            pdc.token_service,
            cp.title
        FROM core_profiledataconfigcatchment pdc
        JOIN core_catchmentpoint cp ON cp.id = pdc.point_catchment_id
        ORDER BY pdc.point_catchment_id
    """)
    local_configs = {row['point_catchment_id']: row for row in local_cursor.fetchall()}
    print(f"   Encontradas {len(local_configs)} configuraciones en local")

    print("\n" + "="*80)
    print("ANÁLISIS DE DIFERENCIAS")
    print("="*80)

    to_update = []
    missing_in_local = []

    for cluster_row in cluster_configs:
        point_id = cluster_row['point_catchment_id']
        cluster_token = cluster_row['token_service']
        title = cluster_row['title']

        if point_id not in local_configs:
            print(f"⚠️  Punto ID:{point_id} ({title}) - Existe en CLUSTER pero NO en LOCAL")
            missing_in_local.append(cluster_row)
            continue

        local_row = local_configs[point_id]
        local_token = local_row['token_service']

        # Comparar tokens
        if cluster_token != local_token:
            if not local_token or local_token.strip() == '':
                print(f"❌ ID:{point_id} - {title} - LOCAL SIN TOKEN")
            else:
                print(f"⚠️  ID:{point_id} - {title} - TOKENS DIFERENTES")

            to_update.append({
                'point_id': point_id,
                'title': title,
                'cluster_token': cluster_token,
                'local_token': local_token,
                'd1': cluster_row['d1'],
                'd2': cluster_row['d2'],
                'd3': cluster_row['d3'],
                'd4': cluster_row['d4'],
                'd5': cluster_row['d5'],
                'd6': cluster_row['d6'],
                'is_telemetry': cluster_row['is_telemetry']
            })

    print("\n" + "="*80)
    print("RESUMEN")
    print("="*80)
    print(f"Configuraciones a actualizar: {len(to_update)}")
    print(f"Configuraciones faltantes en local: {len(missing_in_local)}")

    if not to_update and not missing_in_local:
        print("\n✅ No hay diferencias. Todo está sincronizado.")
        return

    # Confirmar actualización
    print("\n" + "="*80)
    print("⚠️  ACCIÓN REQUERIDA")
    print("="*80)
    print("\n¿Deseas sincronizar desde CLUSTER a LOCAL?")
    print("Esto actualizará tokens y configuraciones en la base de datos local.")
    print("\nOpciones:")
    print("  [1] SÍ - Sincronizar ahora")
    print("  [2] NO - Solo mostrar diferencias")

    choice = input("\nElige [1/2]: ").strip()

    if choice == '1':
        print("\n🔄 Sincronizando...")

        updated_count = 0
        created_count = 0

        # Actualizar configuraciones existentes
        for item in to_update:
            local_cursor.execute("""
                UPDATE core_profiledataconfigcatchment
                SET
                    token_service = %s,
                    d1 = %s,
                    d2 = %s,
                    d3 = %s,
                    d4 = %s,
                    d5 = %s,
                    d6 = %s,
                    is_telemetry = %s
                WHERE point_catchment_id = %s
            """, (
                item['cluster_token'],
                item['d1'], item['d2'], item['d3'],
                item['d4'], item['d5'], item['d6'],
                item['is_telemetry'],
                item['point_id']
            ))
            updated_count += 1
            print(f"✅ ID:{item['point_id']} - {item['title']} - Token actualizado")

        # Crear configuraciones faltantes
        for cluster_row in missing_in_local:
            local_cursor.execute("""
                INSERT INTO core_profiledataconfigcatchment
                (point_catchment_id, token_service, d1, d2, d3, d4, d5, d6, is_telemetry, created, modified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """, (
                cluster_row['point_catchment_id'],
                cluster_row['token_service'],
                cluster_row['d1'], cluster_row['d2'], cluster_row['d3'],
                cluster_row['d4'], cluster_row['d5'], cluster_row['d6'],
                cluster_row['is_telemetry']
            ))
            created_count += 1
            print(f"✅ ID:{cluster_row['point_catchment_id']} - {cluster_row['title']} - Configuración creada")

        # Commit cambios
        local_conn.commit()

        print("\n✅ Sincronización completada:")
        print(f"   Configuraciones actualizadas: {updated_count}")
        print(f"   Configuraciones creadas: {created_count}")
        print(f"   TOTAL: {updated_count + created_count}")

    else:
        print("\n✅ No se realizaron cambios.")

    # Cerrar conexiones
    cluster_cursor.close()
    cluster_conn.close()
    local_cursor.close()
    local_conn.close()

    print("\n" + "="*80)
    print("Script finalizado")
    print("="*80 + "\n")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrumpido por el usuario.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
