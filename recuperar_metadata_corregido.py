#!/usr/bin/env python3
"""
Recuperar metadata del cluster con esquemas correctos
"""
import psycopg2
import os
import sys

def main():
    print("="*60)
    print("RECUPERANDO METADATA DEL CLUSTER")
    print("="*60)
    sys.stdout.flush()

    env = {}
    with open('/app/.env') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, val = line.strip().split('=', 1)
                env[key] = val

    remote_conn = psycopg2.connect(
        host=env['CLUSTER_DB_HOST'],
        port=int(env['CLUSTER_DB_PORT']),
        user=env['CLUSTER_DB_USER'],
        password=env['CLUSTER_DB_PASSWORD'],
        database='data_store_telemetry',
        sslmode='require'
    )

    local_conn = psycopg2.connect(
        host='postgres',
        port=5432,
        user='smarthydro_user',
        password='smarthydro_password_2025',
        database='smarthydro_prod'
    )

    remote_cursor = remote_conn.cursor()
    local_cursor = local_conn.cursor()

    # 1. COPIAR CLIENTES (sin description que no existe en cluster)
    print("\n1️⃣ COPIANDO CLIENTES...")
    sys.stdout.flush()
    remote_cursor.execute("SELECT id, name, created, rut, address, phone, email FROM core_client ORDER BY id")
    clientes = remote_cursor.fetchall()

    for c in clientes:
        try:
            local_cursor.execute("""
                INSERT INTO core_client (id, name, created, rut, address, phone, email)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    rut = EXCLUDED.rut,
                    address = EXCLUDED.address,
                    phone = EXCLUDED.phone,
                    email = EXCLUDED.email
            """, c)
        except Exception as e:
            print(f"  Error cliente {c[0]}: {e}")
            sys.stdout.flush()

    local_conn.commit()
    print(f"  ✅ {len(clientes)} clientes procesados")
    sys.stdout.flush()

    # 2. COPIAR PROYECTOS (sin description, con code_internal)
    print("\n2️⃣ COPIANDO PROYECTOS...")
    sys.stdout.flush()
    remote_cursor.execute("SELECT id, name, created, code_internal, client_id FROM core_projectcatchments ORDER BY id")
    proyectos = remote_cursor.fetchall()

    for p in proyectos:
        try:
            # Local tiene "description", cluster tiene "code_internal"
            local_cursor.execute("""
                INSERT INTO core_projectcatchments (id, name, created, description, client_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    client_id = EXCLUDED.client_id
            """, (p[0], p[1], p[2], p[3], p[4]))  # code_internal -> description
        except Exception as e:
            print(f"  Error proyecto {p[0]}: {e}")
            sys.stdout.flush()

    local_conn.commit()
    print(f"  ✅ {len(proyectos)} proyectos procesados")
    sys.stdout.flush()

    # 3. COPIAR PUNTOS DE CAPTACIÓN (esquema diferente!)
    print("\n3️⃣ COPIANDO PUNTOS DE CAPTACIÓN...")
    sys.stdout.flush()
    remote_cursor.execute("""
        SELECT id, title, created, is_tdata, is_novus, is_thethings,
               project_id, frecuency, lat, lon
        FROM core_catchmentpoint
        ORDER BY id
    """)
    puntos = remote_cursor.fetchall()

    copiados = 0
    for p in puntos:
        try:
            # Cluster: id, title, created, is_tdata, is_novus, is_thethings, project_id, frecuency, lat, lon
            # Local: id, title, description, address, created, project_id, is_tdata, is_novus, is_thethings, frecuency, lat, lon
            local_cursor.execute("""
                INSERT INTO core_catchmentpoint
                (id, title, description, address, created, project_id,
                 is_tdata, is_novus, is_thethings, frecuency, lat, lon)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    project_id = EXCLUDED.project_id,
                    is_tdata = EXCLUDED.is_tdata,
                    is_novus = EXCLUDED.is_novus,
                    is_thethings = EXCLUDED.is_thethings,
                    frecuency = EXCLUDED.frecuency,
                    lat = EXCLUDED.lat,
                    lon = EXCLUDED.lon
            """, (p[0], p[1], '', '', p[2], p[6], p[3], p[4], p[5], p[7], p[8], p[9]))
            copiados += 1
        except Exception as e:
            print(f"  Error punto {p[0]} ({p[1]}): {e}")
            sys.stdout.flush()

    local_conn.commit()
    print(f"  ✅ {copiados}/{len(puntos)} puntos copiados")
    sys.stdout.flush()

    # 4. COPIAR ESQUEMAS
    print("\n4️⃣ COPIANDO ESQUEMAS...")
    sys.stdout.flush()
    remote_cursor.execute("SELECT id, name, description, created FROM core_schemescatchment ORDER BY id")
    esquemas = remote_cursor.fetchall()

    for e in esquemas:
        try:
            local_cursor.execute("""
                INSERT INTO core_schemescatchment (id, name, description, created)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description
            """, e)
        except Exception as ex:
            print(f"  Error esquema {e[0]}: {ex}")
            sys.stdout.flush()

    local_conn.commit()
    print(f"  ✅ {len(esquemas)} esquemas procesados")
    sys.stdout.flush()

    # 5. COPIAR VARIABLES (esquema MUY diferente - necesitamos mapeo cuidadoso)
    print("\n5️⃣ COPIANDO VARIABLES...")
    sys.stdout.flush()
    print("  ⚠️  NOTA: Esquemas de variables son incompatibles, copiando solo campos comunes")
    sys.stdout.flush()

    remote_cursor.execute("""
        SELECT id, created, label, type_variable, scheme_catchment_id
        FROM core_variable
        ORDER BY id
    """)
    variables = remote_cursor.fetchall()

    for v in variables:
        try:
            # Mapeo básico: cluster(id, created, label, type_variable, scheme_id) -> local(id, name, created, type_variable, unit, total_mode, scheme_id, pos_trama)
            local_cursor.execute("""
                INSERT INTO core_variable
                (id, name, created, type_variable, unit, total_mode, scheme_catchment_id, pos_trama)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    type_variable = EXCLUDED.type_variable,
                    scheme_catchment_id = EXCLUDED.scheme_catchment_id
            """, (v[0], v[2], v[1], v[3], '', '', v[4], 0))  # label->name, defaults para campos faltantes
        except Exception as e:
            print(f"  Error variable {v[0]}: {e}")
            sys.stdout.flush()

    local_conn.commit()
    print(f"  ✅ {len(variables)} variables procesadas")
    sys.stdout.flush()

    # 6. COPIAR RELACIÓN ESQUEMAS-PUNTOS
    print("\n6️⃣ COPIANDO RELACIONES ESQUEMAS-PUNTOS...")
    sys.stdout.flush()
    remote_cursor.execute("""
        SELECT schemescatchment_id, catchmentpoint_id
        FROM core_schemescatchment_points_catchment
    """)
    relaciones = remote_cursor.fetchall()

    for r in relaciones:
        try:
            local_cursor.execute("""
                INSERT INTO core_schemescatchment_points_catchment
                (schemescatchment_id, catchmentpoint_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, r)
        except Exception as e:
            pass

    local_conn.commit()
    print(f"  ✅ {len(relaciones)} relaciones procesadas")
    sys.stdout.flush()

    # 7. COPIAR CONFIGURACIONES DGA (campos diferentes!)
    print("\n7️⃣ COPIANDO CONFIGURACIONES DGA...")
    sys.stdout.flush()
    print("  ⚠️  NOTA: Copiando solo campos compatibles")
    sys.stdout.flush()

    remote_cursor.execute("""
        SELECT id, code_dga, standard, point_catchment_id,
               send_dga, flow_granted_dga, created
        FROM core_dgadataconfigcatchment
        ORDER BY id
    """)
    dga_configs = remote_cursor.fetchall()

    for d in dga_configs:
        try:
            # Cluster: id, code_dga, standard, point_id, send_dga, flow_granted, created
            # Local: id, code_dga, standard, frecuency_dga, point_id, send_dga, flow_granted, right_number, created
            local_cursor.execute("""
                INSERT INTO core_dgadataconfigcatchment
                (id, code_dga, standard, frecuency_dga, point_catchment_id,
                 send_dga, flow_granted_dga, right_number, created)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    code_dga = EXCLUDED.code_dga,
                    standard = EXCLUDED.standard,
                    send_dga = EXCLUDED.send_dga,
                    flow_granted_dga = EXCLUDED.flow_granted_dga
            """, (d[0], d[1], d[2], '', d[3], d[4], d[5], '', d[6]))  # defaults para campos faltantes
        except Exception as e:
            print(f"  Error config DGA {d[0]}: {e}")
            sys.stdout.flush()

    local_conn.commit()
    print(f"  ✅ {len(dga_configs)} configuraciones DGA procesadas")
    sys.stdout.flush()

    # 8. COPIAR PERFILES (esquema diferente!)
    print("\n8️⃣ COPIANDO PERFILES...")
    sys.stdout.flush()
    print("  ⚠️  NOTA: Copiando solo campos numéricos compatibles")
    sys.stdout.flush()

    remote_cursor.execute("""
        SELECT id, point_catchment_id, is_telemetry,
               d1, d2, d3, d4, d5, d6, date_delivery_act, created
        FROM core_profiledataconfigcatchment
        ORDER BY id
    """)
    perfiles = remote_cursor.fetchall()

    for p in perfiles:
        try:
            # Cluster: id, point_id, is_telemetry, d1-d6, date_delivery, created
            # Local: id, k, point_id, is_telemetry, addition, d1-d6, date_delivery, created
            local_cursor.execute("""
                INSERT INTO core_profiledataconfigcatchment
                (id, k, point_catchment_id, is_telemetry, addition,
                 d1, d2, d3, d4, d5, d6, date_delivery_act, created)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    is_telemetry = EXCLUDED.is_telemetry,
                    d1 = EXCLUDED.d1,
                    d2 = EXCLUDED.d2,
                    d3 = EXCLUDED.d3,
                    d4 = EXCLUDED.d4,
                    d5 = EXCLUDED.d5,
                    d6 = EXCLUDED.d6,
                    date_delivery_act = EXCLUDED.date_delivery_act
            """, (p[0], 0, p[1], p[2], 0, p[3], p[4], p[5], p[6], p[7], p[8], p[9], p[10]))  # defaults para k y addition
        except Exception as e:
            print(f"  Error perfil {p[0]}: {e}")
            sys.stdout.flush()

    local_conn.commit()
    print(f"  ✅ {len(perfiles)} perfiles procesados")
    sys.stdout.flush()

    remote_cursor.close()
    local_cursor.close()
    remote_conn.close()
    local_conn.close()

    print("\n✅ METADATA RECUPERADA")
    print("Ahora reintenta recuperar los datos de mediciones")
    sys.stdout.flush()

if __name__ == '__main__':
    main()
