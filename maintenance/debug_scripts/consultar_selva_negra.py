import sqlite3
import json
from datetime import datetime
import sys
sys.path.append('/root/core_api_sh')

print("=== DATOS ACTUALES DE SELVA NEGRA (ID: 156) ===\n")

try:
    # Intentar conectar con SQLite
    db_path = "/root/core_api_sh/db.sqlite3"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Información básica del punto
    print("📍 INFORMACIÓN BÁSICA:")
    cursor.execute("""
        SELECT id, name, profile_data_config, user_id, client_id
        FROM core_catchmentpoint 
        WHERE id = 156
    """)
    punto = cursor.fetchone()
    if punto:
        print(f"   ID: {punto[0]}")
        print(f"   Nombre: {punto[1]}")
        print(f"   Profile data config: {punto[2]}")
        print(f"   User ID: {punto[3]}")
        print(f"   Client ID: {punto[4]}")
    
    # Configuración de perfil de datos
    print("\n🔧 CONFIGURACIÓN DE PERFIL:")
    cursor.execute("""
        SELECT d1, d2, d3, token_service, pulses_factor
        FROM core_profiledataconfigcatchment 
        WHERE point_catchment_id = 156
    """)
    profile = cursor.fetchone()
    if profile:
        print(f"   d1 (Profundidad): {profile[0]}")
        print(f"   d2 (Posicionamiento bomba): {profile[1]}")
        print(f"   d3 (Posicionamiento nivel): {profile[2]} ⭐")
        print(f"   Token service: {profile[3]}")
        print(f"   Pulses factor: {profile[4]}")
    
    # Variables configuradas
    print("\n📊 VARIABLES CONFIGURADAS:")
    cursor.execute("""
        SELECT str_variable, label, type_variable, token_service, service, calculate_nivel
        FROM core_variable 
        WHERE point_catchment_id = 156
    """)
    variables = cursor.fetchall()
    for var in variables:
        print(f"   Variable: {var[0]}")
        print(f"   Label: {var[1]}")
        print(f"   Tipo: {var[2]}")
        print(f"   Token: {var[3]}")
        print(f"   Servicio: {var[4]}")
        print(f"   Calculate nivel: {var[5]}")
        print(f"   ---")
    
    # Últimos registros guardados
    print("\n💾 ÚLTIMOS 5 REGISTROS GUARDADOS:")
    cursor.execute("""
        SELECT date_time_medition, nivel, water_table, date_time_last_logger
        FROM core_interactiondetail 
        WHERE catchment_point_id = 156 
        ORDER BY date_time_medition DESC 
        LIMIT 5
    """)
    registros = cursor.fetchall()
    for reg in registros:
        print(f"   {reg[0]} | Nivel: {reg[1]} | Water table: {reg[2]} | Logger: {reg[3]}")
    
    conn.close()
    
except Exception as e:
    print(f"Error consultando BD: {e}")

