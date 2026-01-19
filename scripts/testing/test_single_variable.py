#!/usr/bin/env python3
"""
Test de una sola variable para identificar el error exacto
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.cronjobs.telemetry.novus_dynamic import get_data_with_retry_dynamic

print("🧪 TEST SOLO UNA VARIABLE")
print("=" * 40)

# Usar punto 2 que sabemos que existe
point_id = 2
provider_name = "nettra"
variable_name = "nivel"

print(f"Punto: {point_id}, Provider: {provider_name}, Variable: {variable_name}")

try:
    result = get_data_with_retry_dynamic(
        point_id=point_id,
        provider_name=provider_name,
        variable_name=variable_name
    )
    print(f"Resultado: {result}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()