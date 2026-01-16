#!/usr/bin/env python3
"""
Recuperar metadatos (Clientes, Puntos, Variables, Configs) del cluster remoto.
Version V3:
 - Maneja fallback de owner_user_id si el usuario no existe.
 - Inserta default para 'addition' en ProfileDataConfig.
"""
import psycopg2
import os
import sys

def main():
    print("="*60)
    print("RECUPERANDO METADATA (V3)")
    print("="*60)
    sys.stdout.flush()

    env = {}
    with open('/app/.env') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, val = line.strip().split('=', 1)
                env[key] = val

    print("Connecting to remote...")
    remote_conn = psycopg2.connect(
        host=env['CLUSTER_DB_HOST'],
        port=int(env['CLUSTER_DB_PORT']),
        user=env['CLUSTER_DB_USER'],
        password=env['CLUSTER_DB_PASSWORD'],
        database='data_store_telemetry',
        sslmode='require'
    )

    print("Connecting to local...")
    local_conn = psycopg2.connect(
        host='postgres',
        port=5432,
        user='smarthydro_user',
        password='smarthydro_password_2025',
        database='smarthydro_prod'
    )

    remote_cursor = remote_conn.cursor()
    local_cursor = local_conn.cursor()

    valid_user_ids = set()

    # 0. USUARIOS
    print("\n0️⃣ COPIANDO USUARIOS...")
    remote_cursor.execute("""
        SELECT id, password, last_login, is_superuser, username, first_name, last_name, is_staff, is_active, date_joined, created, modified, email, txt_password, is_verified
        FROM core_user ORDER BY id
    """)
    rows = remote_cursor.fetchall()
    for r in rows:
        user_id = r[0]
        valid_user_ids.add(user_id)
        try:
            local_cursor.execute("""
                INSERT INTO core_user 
                (id, password, last_login, is_superuser, username, first_name, last_name, is_staff, is_active, date_joined, created, modified, email, txt_password, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    password = EXCLUDED.password,
                    last_login = EXCLUDED.last_login,
                    is_superuser = EXCLUDED.is_superuser,
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    is_staff = EXCLUDED.is_staff,
                    is_active = EXCLUDED.is_active,
                    date_joined = EXCLUDED.date_joined,
                    created = EXCLUDED.created,
                    modified = EXCLUDED.modified,
                    email = EXCLUDED.email,
                    txt_password = EXCLUDED.txt_password,
                    is_verified = EXCLUDED.is_verified
            """, r)
        except Exception as e:
            print(f"Error usuario {user_id}: {e}")
            local_conn.rollback()
    
    # Ensure ID 1 exists as fallback
    if 1 not in valid_user_ids:
        print("Warning: User ID 1 not found in remote. Ensuring it exists locally for fallback.")
        try:
            local_cursor.execute("SELECT id FROM core_user WHERE id=1")
            if not local_cursor.fetchone():
                # Create dummy admin if not exists
                local_cursor.execute("""
                    INSERT INTO core_user (id, username, password, is_active, is_staff, is_superuser, created, modified, date_joined)
                    VALUES (1, 'admin_fallback', 'fallback', true, true, true, NOW(), NOW(), NOW())
                """)
                local_conn.commit()
            valid_user_ids.add(1)
        except Exception as e:
            print(f"Error creating fallback user: {e}")
            local_conn.rollback()

    local_conn.commit()
    print(f"✅ {len(rows)} usuarios procesados")

    # 1. CLIENTES
    print("\n1️⃣ COPIANDO CLIENTES...")
    remote_cursor.execute("SELECT id, created, modified, name, rut, address, phone, email FROM core_client ORDER BY id")
    rows = remote_cursor.fetchall()
    for r in rows:
        try:
            local_cursor.execute("""
                INSERT INTO core_client (id, created, modified, name, rut, address, phone, email)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    modified = EXCLUDED.modified,
                    name = EXCLUDED.name,
                    rut = EXCLUDED.rut,
                    address = EXCLUDED.address,
                    phone = EXCLUDED.phone,
                    email = EXCLUDED.email
            """, r)
        except Exception as e:
            print(f"Error cliente {r[0]}: {e}")
            local_conn.rollback()
    local_conn.commit()
    print(f"✅ {len(rows)} clientes procesados")

    # 2. PROYECTOS
    print("\n2️⃣ COPIANDO PROYECTOS...")
    remote_cursor.execute("SELECT id, created, modified, name, code_internal, client_id FROM core_projectcatchments ORDER BY id")
    rows = remote_cursor.fetchall()
    for r in rows:
        try:
            local_cursor.execute("""
                INSERT INTO core_projectcatchments (id, created, modified, name, code_internal, client_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    modified = EXCLUDED.modified,
                    name = EXCLUDED.name,
                    code_internal = EXCLUDED.code_internal,
                    client_id = EXCLUDED.client_id
            """, r)
        except Exception as e:
            print(f"Error proyecto {r[0]}: {e}")
            local_conn.rollback()
    local_conn.commit()
    print(f"✅ {len(rows)} proyectos procesados")

    # 3. PUNTOS
    print("\n3️⃣ COPIANDO PUNTOS...")
    remote_cursor.execute("""
        SELECT id, created, modified, title, is_thethings, is_tdata, is_novus, lat, lon, frecuency, project_id, owner_user_id
        FROM core_catchmentpoint ORDER BY id
    """)
    rows = remote_cursor.fetchall()
    for r in rows:
        # r = (id, created, modified, title, is_thethings, is_tdata, is_novus, lat, lon, frecuency, project_id, owner_user_id)
        r_list = list(r)
        owner_id = r_list[11]
        
        if owner_id not in valid_user_ids:
            # Fallback to 1
            r_list[11] = 1
        
        try:
            local_cursor.execute("""
                INSERT INTO core_catchmentpoint 
                (id, created, modified, title, is_thethings, is_tdata, is_novus, lat, lon, frecuency, project_id, owner_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    modified = EXCLUDED.modified,
                    title = EXCLUDED.title,
                    is_thethings = EXCLUDED.is_thethings,
                    is_tdata = EXCLUDED.is_tdata,
                    is_novus = EXCLUDED.is_novus,
                    lat = EXCLUDED.lat,
                    lon = EXCLUDED.lon,
                    frecuency = EXCLUDED.frecuency,
                    project_id = EXCLUDED.project_id,
                    owner_user_id = EXCLUDED.owner_user_id
            """, tuple(r_list))
        except Exception as e:
            print(f"Error punto {r[0]}: {e}")
            local_conn.rollback()
    local_conn.commit()
    print(f"✅ {len(rows)} puntos procesados")

    # 4. ESQUEMAS
    print("\n4️⃣ COPIANDO ESQUEMAS...")
    remote_cursor.execute("SELECT id, created, modified, name, description FROM core_schemescatchment ORDER BY id")
    rows = remote_cursor.fetchall()
    for r in rows:
        try:
            local_cursor.execute("""
                INSERT INTO core_schemescatchment (id, created, modified, name, description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    modified = EXCLUDED.modified,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description
            """, r)
        except Exception as e:
            # Often id passed is not unique? No id is PK.
            print(f"Error esquema {r[0]}: {e}")
            local_conn.rollback()
    local_conn.commit()
    print(f"✅ {len(rows)} esquemas procesados")

    # 5. VARIABLES
    print("\n5️⃣ COPIANDO VARIABLES...")
    remote_cursor.execute("""
        SELECT id, created, modified, str_variable, label, type_variable, token_service, service, 
               pulses_factor, convert_to_lt, calculate_nivel, scheme_catchment_id
        FROM core_variable ORDER BY id
    """)
    rows = remote_cursor.fetchall()
    for r in rows:
        try:
            local_cursor.execute("""
                INSERT INTO core_variable 
                (id, created, modified, str_variable, label, type_variable, token_service, service,
                 pulses_factor, convert_to_lt, calculate_nivel, scheme_catchment_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    modified = EXCLUDED.modified,
                    str_variable = EXCLUDED.str_variable,
                    label = EXCLUDED.label,
                    type_variable = EXCLUDED.type_variable,
                    token_service = EXCLUDED.token_service,
                    service = EXCLUDED.service,
                    pulses_factor = EXCLUDED.pulses_factor,
                    convert_to_lt = EXCLUDED.convert_to_lt,
                    calculate_nivel = EXCLUDED.calculate_nivel,
                    scheme_catchment_id = EXCLUDED.scheme_catchment_id
            """, r)
        except Exception as e:
            print(f"Error variable {r[0]}: {e}")
            local_conn.rollback()
    local_conn.commit()
    print(f"✅ {len(rows)} variables procesadas")

    # 6. RELACIÓN ESQUEMAS-PUNTOS
    print("\n6️⃣ COPIANDO RELACIONES ESQUEMAS-PUNTOS...")
    try:
        remote_cursor.execute("SELECT schemescatchment_id, catchmentpoint_id FROM core_schemescatchment_points_catchment")
        rows = remote_cursor.fetchall()
        for r in rows:
            try:
                local_cursor.execute("""
                    INSERT INTO core_schemescatchment_points_catchment (schemescatchment_id, catchmentpoint_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, r)
            except Exception as e:
                local_conn.rollback()
        local_conn.commit()
        print(f"✅ {len(rows)} relaciones procesadas")
    except Exception as e:
        print(f"Error relaciones: {e}")
        local_conn.rollback()

    # 7. DGA CONFIG
    print("\n7️⃣ COPIANDO DGA CONFIG...")
    remote_cursor.execute("""
        SELECT id, created, modified, send_dga, standard, type_dga, code_dga, flow_granted_dga, total_granted_dga, 
               shac, date_start_compliance, date_created_code, name_informant, rut_report_dga, password_dga_software, point_catchment_id
        FROM core_dgadataconfigcatchment ORDER BY id
    """)
    rows = remote_cursor.fetchall()
    for r in rows:
        try:
            local_cursor.execute("""
                INSERT INTO core_dgadataconfigcatchment
                (id, created, modified, send_dga, standard, type_dga, code_dga, flow_granted_dga, total_granted_dga,
                 shac, date_start_compliance, date_created_code, name_informant, rut_report_dga, password_dga_software, point_catchment_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    modified = EXCLUDED.modified,
                    send_dga = EXCLUDED.send_dga,
                    standard = EXCLUDED.standard,
                    type_dga = EXCLUDED.type_dga,
                    code_dga = EXCLUDED.code_dga,
                    flow_granted_dga = EXCLUDED.flow_granted_dga,
                    total_granted_dga = EXCLUDED.total_granted_dga,
                    shac = EXCLUDED.shac,
                    date_start_compliance = EXCLUDED.date_start_compliance,
                    date_created_code = EXCLUDED.date_created_code,
                    name_informant = EXCLUDED.name_informant,
                    rut_report_dga = EXCLUDED.rut_report_dga,
                    password_dga_software = EXCLUDED.password_dga_software,
                    point_catchment_id = EXCLUDED.point_catchment_id
            """, r)
        except Exception as e:
            print(f"Error DGA config {r[0]}: {e}")
            local_conn.rollback()
    local_conn.commit()
    print(f"✅ {len(rows)} DGA configs procesadas")

    # 8. PROFILE DATA CONFIG
    print("\n8️⃣ COPIANDO PROFILE DATA CONFIG...")
    # NOTE: Inserting 0 for addition
    remote_cursor.execute("""
        SELECT id, created, modified, token_service, d1, d2, d3, d4, d5, d6, is_telemetry, date_start_telemetry, date_delivery_act, point_catchment_id
        FROM core_profiledataconfigcatchment ORDER BY id
    """)
    rows = remote_cursor.fetchall()
    for r in rows:
        # r has 14 elements.
        try:
            local_cursor.execute("""
                INSERT INTO core_profiledataconfigcatchment
                (id, created, modified, token_service, d1, d2, d3, d4, d5, d6, is_telemetry, date_start_telemetry, date_delivery_act, point_catchment_id, addition)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                ON CONFLICT (id) DO UPDATE SET
                    modified = EXCLUDED.modified,
                    token_service = EXCLUDED.token_service,
                    d1 = EXCLUDED.d1,
                    d2 = EXCLUDED.d2,
                    d3 = EXCLUDED.d3,
                    d4 = EXCLUDED.d4,
                    d5 = EXCLUDED.d5,
                    d6 = EXCLUDED.d6,
                    is_telemetry = EXCLUDED.is_telemetry,
                    date_start_telemetry = EXCLUDED.date_start_telemetry,
                    date_delivery_act = EXCLUDED.date_delivery_act,
                    point_catchment_id = EXCLUDED.point_catchment_id,
                    addition = EXCLUDED.addition
            """, r)
        except Exception as e:
            print(f"Error Profile config {r[0]}: {e}")
            local_conn.rollback()
    local_conn.commit()
    print(f"✅ {len(rows)} Profile configs procesadas")

    print("\n✅ METADATA RECUPERADA EXITOSAMENTE (V3)")

if __name__ == '__main__':
    main()
