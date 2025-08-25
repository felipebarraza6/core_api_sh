
def create_core_table_if_not_exists(local_cursor, cluster_cursor, table_name, db_name):
    """Crear tabla core_ si no existe, copiando estructura del local"""
    try:
        # Verificar si existe en cluster
        cluster_cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = %s AND table_schema = 'public'
            )
        """, (table_name,))
        
        if cluster_cursor.fetchone()[0]:
            print(f"✅ {db_name}: {table_name} ya existe")
            return True
        
        # Obtener CREATE TABLE del local
        local_cursor.execute(f"""
            SELECT 
                'CREATE TABLE ' || table_name || ' (' ||
                string_agg(
                    column_name || ' ' || data_type ||
                    CASE 
                        WHEN character_maximum_length IS NOT NULL 
                        THEN '(' || character_maximum_length || ')'
                        WHEN numeric_precision IS NOT NULL AND numeric_scale IS NOT NULL
                        THEN '(' || numeric_precision || ',' || numeric_scale || ')'
                        ELSE ''
                    END ||
                    CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END,
                    ', '
                ) || ');'
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' AND table_schema = 'public'
            GROUP BY table_name
        """)
        
        create_sql = local_cursor.fetchone()
        if not create_sql:
            print(f"❌ {db_name}: No se pudo obtener estructura de {table_name}")
            return False
        
        # Crear tabla en cluster
        cluster_cursor.execute(create_sql[0])
        
        # Crear índices básicos (solo PK por ahora)
        try:
            cluster_cursor.execute(f"""
                ALTER TABLE {table_name} 
                ADD CONSTRAINT {table_name}_pkey PRIMARY KEY (id)
            """)
        except:
            pass  # PK puede ya existir o no ser necesario
        
        print(f"✅ {db_name}: {table_name} creada exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ {db_name}: Error creando {table_name}: {e}")
        return False

def ensure_core_tables_exist(local_cursor, cluster_cursor, db_name):
    """Asegurar que todas las tablas core_ existen en el cluster"""
    print(f"🔧 {db_name}: Verificando/creando tablas core_...")
    
    created_count = 0
    
    for table_name in CORE_OPERATIONAL_TABLES + ['core_interactiondetail']:
        if create_core_table_if_not_exists(local_cursor, cluster_cursor, table_name, db_name):
            created_count += 1
    
    print(f"✅ {db_name}: {created_count}/{len(CORE_OPERATIONAL_TABLES) + 1} tablas verificadas/creadas")
    return created_count == len(CORE_OPERATIONAL_TABLES) + 1
