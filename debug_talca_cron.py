
import os
import django
import sys
import time

# Container Setup
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint
from api.cronjobs.telemetry.controllers.nivel import nivel_mt, water_table

def verify_130_case():
    print("--- VERIFYING USER REPORTED CASE (131 -> 1.30) ---")
    
    # Datos reportados por usuario para Ñiquen
    val = 131   # Valor crudo
    base = 100  # Base cálculo
    d3 = 8.30   # D3 (Depth)
    point_id = 999 

    print(f"Input Value: {val}")
    print(f"Base: {base}")
    print(f"D3: {d3}")

    # Paso 1: Nivel en metros
    # Debería ser 131 / 100 = 1.31
    calculated_nivel_str = nivel_mt(val, base, point_id, d3)
    print(f"Calculated Nivel (Str): '{calculated_nivel_str}'")
    
    try:
        calculated_nivel = float(calculated_nivel_str)
    except ValueError:
        print("ERROR: Result is not a valid float")
        return

    expected_nivel = 1.31
    if abs(calculated_nivel - expected_nivel) < 0.01:
        print("✅ Nivel calculation CORRECT (1.31)")
    else:
        print(f"❌ Nivel calculation INCORRECT. Got {calculated_nivel}, expected {expected_nivel}")

    # Paso 2: Nivel Freático
    # Debería ser 8.30 - 1.31 = 6.99
    wt_str = water_table(calculated_nivel, d3)
    print(f"Calculated Water Table: '{wt_str}'")
    
    try:
        wt = float(wt_str)
    except ValueError:
        print("ERROR: WT Result is not a valid float")
        return

    expected_wt = 6.99
    if abs(wt - expected_wt) < 0.01:
        print("✅ Water Table calculation CORRECT (6.99)")
    else:
        print(f"❌ Water Table calculation INCORRECT. Got {wt}, expected {expected_wt}")

    if wt == 0.00:
        print("❌ FAIL: System returned 0.00 (User report confirmed?)")
    else:
        print("✅ PASS: System did NOT return 0.00")

if __name__ == "__main__":
    verify_130_case()
