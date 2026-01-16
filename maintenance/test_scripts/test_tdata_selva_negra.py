import sys
sys.path.append('/root/core_api_sh')

from api.cronjobs.telemetry.getters.tdata import get_data_tdata

# Necesito encontrar el token y variable de Selva Negra
# Vamos a buscar en archivos de configuración

print("=== TESTE TDATA PARA SELVA NEGRA ===")

# Primero intentemos con algunos tokens típicos y variables comunes
test_tokens = ["your_token", "selva_negra_token", "device_token"]
test_variables = ["nivel", "level", "water_level", "h1", "h2"]

for token in test_tokens:
    for variable in test_variables:
        try:
            print(f"\nProbando token: {token}, variable: {variable}")
            data = get_data_tdata(token, variable)
            print(f"Resultado: {data}")
        except Exception as e:
            print(f"Error: {e}")
            continue

