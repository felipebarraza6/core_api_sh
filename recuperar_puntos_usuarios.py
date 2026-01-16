#!/usr/bin/env python3
"""
Recuperar puntos de captación, usuarios, variables y esquemas del cluster
"""
import psycopg2
import os
import sys

def main():
    print("="*60)
    print("RECUPERANDO PUNTOS, USUARIOS Y CONFIGURACIONES")
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

    # COPIAR CLIENTES
    print("\n1️⃣ COPIANDO CLIENTES...")
    remote_cursor.execute("SELECT id, name, created, NULL, address, phone FROM core_client ORDER BY id")
    clientes = remote_cursor.fetchall()

    for c in clientes:
        try:
            local_cursor.execute("""
                INSERT INTO core_client (id, name, created, description, address, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    address = EXCLUDED.address,
                    phone = EXCLUDED.phone
            """, c)
        except Exception as e:
            print(f"  Error cliente {c[0]}: {e}")

    local_conn.commit()
    print(f"  ✅ {len(clientes)} clientes procesados")

    # COPIAR PROYECTOS
    print("\n2️⃣ COPIANDO PROYECTOS...")
    remote_cursor.execute("SELECT id, name, NULL, created, client_id FROM core_projectcatchments ORDER BY id")
    proyectos = remote_cursor.fetchall()

    for p in proyectos:
        try:
            local_cursor.execute("""
                INSERT INTO core_projectcatchments (id, name, description, created, client_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    client_id = EXCLUDED.client_id
            """, p)
        except Exception as e:
            print(f"  Error proyecto {p[0]}: {e}")

    local_conn.commit()
    print(f"  ✅ {len(proyectos)} proyectos procesados")

    # COPIAR PUNTOS DE CAPTACIÓN
    print("\n3️⃣ COPIANDO PUNTOS DE CAPTACIÓN...")
    remote_cursor.execute("""
        SELECT id, title, NULL, NULL, created, project_id,
               is_tdata, is_novus, is_thethings, frecuency, lat, lon
        FROM core_catchmentpoint
        ORDER BY id
    """)
    puntos = remote_cursor.fetchall()

    copiados = 0
    for p in puntos:
        try:
            local_cursor.execute("""
                INSERT INTO core_catchmentpoint
                (id, title, description, address, created, project_id,
                 is_tdata, is_novus, is_thethings, frecuency, lat, lon)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    address = EXCLUDED.address,
                    project_id = EXCLUDED.project_id,
                    is_tdata = EXCLUDED.is_tdata,
                    is_novus = EXCLUDED.is_novus,
                    is_thethings = EXCLUDED.is_thethings,
                    frecuency = EXCLUDED.frecuency,
                    lat = EXCLUDED.lat,
                    lon = EXCLUDED.lon
            """, p)
            copiados += 1
        except Exception as e:
            print(f"  Error punto {p[0]} ({p[1]}): {e}")

    local_conn.commit()
    print(f"  ✅ {copiados}/{len(puntos)} puntos copiados")

    # COPIAR ESQUEMAS
    print("\n4️⃣ COPIANDO ESQUEMAS...")
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

    local_conn.commit()
    print(f"  ✅ {len(esquemas)} esquemas procesados")

    # COPIAR VARIABLES
    print("\n5️⃣ COPIANDO VARIABLES...")
    remote_cursor.execute("""
        SELECT id, name, created, type_variable, unit,
               total_mode, scheme_catchment_id, pos_trama
        FROM core_variable
        ORDER BY id
    """)
    variables = remote_cursor.fetchall()

    for v in variables:
        try:
            local_cursor.execute("""
                INSERT INTO core_variable
                (id, name, created, type_variable, unit, total_mode, scheme_catchment_id, pos_trama)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    type_variable = EXCLUDED.type_variable,
                    unit = EXCLUDED.unit,
                    total_mode = EXCLUDED.total_mode,
                    scheme_catchment_id = EXCLUDED.scheme_catchment_id,
                    pos_trama = EXCLUDED.pos_trama
            """, v)
        except Exception as e:
            print(f"  Error variable {v[0]}: {e}")

    local_conn.commit()
    print(f"  ✅ {len(variables)} variables procesadas")

    # COPIAR RELACIÓN ESQUEMAS-PUNTOS
    print("\n6️⃣ COPIANDO RELACIONES ESQUEMAS-PUNTOS...")
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

    # COPIAR CONFIGURACIONES DGA
    print("\n7️⃣ COPIANDO CONFIGURACIONES DGA...")
    remote_cursor.execute("""
        SELECT id, code_dga, standard, frecuency_dga, point_catchment_id,
               send_dga, flow_granted_dga, right_number, created
        FROM core_dgadataconfigcatchment
        ORDER BY id
    """)
    dga_configs = remote_cursor.fetchall()

    for d in dga_configs:
        try:
            local_cursor.execute("""
                INSERT INTO core_dgadataconfigcatchment
                (id, code_dga, standard, frecuency_dga, point_catchment_id,
                 send_dga, flow_granted_dga, right_number, created)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    code_dga = EXCLUDED.code_dga,
                    standard = EXCLUDED.standard,
                    frecuency_dga = EXCLUDED.frecuency_dga,
                    send_dga = EXCLUDED.send_dga,
                    flow_granted_dga = EXCLUDED.flow_granted_dga,
                    right_number = EXCLUDED.right_number
            """, d)
        except Exception as e:
            print(f"  Error config DGA {d[0]}: {e}")

    local_conn.commit()
    print(f"  ✅ {len(dga_configs)} configuraciones DGA procesadas")

    # COPIAR PERFILES
    print("\n8️⃣ COPIANDO PERFILES...")
    remote_cursor.execute("""
        SELECT id, k, point_catchment_id, is_telemetry, addition,
               d1, d2, d3, d4, d5, d6, date_delivery_act, created
        FROM core_profiledataconfigcatchment
        ORDER BY id
    """)
    perfiles = remote_cursor.fetchall()

    for p in perfiles:
        try:
            local_cursor.execute("""
                INSERT INTO core_profiledataconfigcatchment
                (id, k, point_catchment_id, is_telemetry, addition,
                 d1, d2, d3, d4, d5, d6, date_delivery_act, created)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    k = EXCLUDED.k,
                    is_telemetry = EXCLUDED.is_telemetry,
                    addition = EXCLUDED.addition,
                    d1 = EXCLUDED.d1,
                    d2 = EXCLUDED.d2,
                    d3 = EXCLUDED.d3,
                    d4 = EXCLUDED.d4,
                    d5 = EXCLUDED.d5,
                    d6 = EXCLUDED.d6,
                    date_delivery_act = EXCLUDED.date_delivery_act
            """, p)
        except Exception as e:
            print(f"  Error perfil {p[0]}: {e}")

    local_conn.commit()
    print(f"  ✅ {len(perfiles)} perfiles procesados")

    remote_cursor.close()
    local_cursor.close()
    remote_conn.close()
    local_conn.close()

    print("\n✅ CONFIGURACIONES RECUPERADAS")
    print("Ahora las mediciones deberían verse correctamente")

if __name__ == '__main__':
    main()
