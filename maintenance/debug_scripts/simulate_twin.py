#!/usr/bin/env python3
"""
Script para simular la lógica del cronjob twin para el punto 161
"""

import os
import django
from datetime import datetime
import pytz

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, DgaDataConfigCatchment

def validate_frequency(point_catchment, current_time):
    """Validar si debe procesar según estándar"""
    try:
        get = DgaDataConfigCatchment.objects.get(point_catchment__id=point_catchment["id"])
        standard = get.standard

        if standard == "MAYOR":
            return current_time.minute == 0  # Cada hora
        elif standard == "MEDIO":
            return current_time.hour == 0 and current_time.minute == 0  # Diario
        elif standard == "MENOR":
            return (current_time.day == 1 and current_time.hour == 0 and current_time.minute == 0)  # Mensual
        elif standard == "CAUDALES_MUY_PEQUENOS":
            return (current_time.month in [1, 7] and current_time.day == 1 and current_time.hour == 0 and current_time.minute == 0)  # Semestral

        return True  # SIN_ESTANDAR siempre procesa
    except Exception as e:
        print(f"Error validando frecuencia: {e}")
        return True

def simulate_twin_logic():
    print("🔍 SIMULANDO LÓGICA TWIN PARA PUNTO 161")
    print("=" * 50)
    
    # Configuración del punto
    point_catchment = {"id": 161}
    
    # Obtener configuración DGA
    try:
        get = DgaDataConfigCatchment.objects.get(point_catchment__id=161)
        print(f"Config DGA encontrada: send_dga={get.send_dga}, standard={get.standard}")
    except Exception as e:
        print(f"Error obteniendo configuración DGA: {e}")
        return
    
    # Simular diferentes horas
    chile_tz = pytz.timezone("America/Santiago")
    current_time = datetime.now(chile_tz)
    
    print(f"\nHora actual: {current_time}")
    print(f"Minuto actual: {current_time.minute}")
    
    # Simular validación para las últimas horas
    print("\nSimulando validación para las últimas horas:")
    for hour in [14, 15, 16, 17, 18, 19]:
        check_time = current_time.replace(hour=hour, minute=0, second=0, microsecond=0)
        freq_valid = validate_frequency(point_catchment, check_time)
        should_send = get.send_dga and freq_valid
        print(f"  {hour}:00 - Frecuencia válida: {freq_valid}, Debería enviar: {should_send}")
    
    # Verificar si hay algún problema con la función
    print(f"\nVerificando función validate_frequency:")
    print(f"  get.send_dga: {get.send_dga}")
    print(f"  validate_frequency para hora actual: {validate_frequency(point_catchment, current_time)}")
    print(f"  Resultado final: {get.send_dga and validate_frequency(point_catchment, current_time)}")

if __name__ == "__main__":
    simulate_twin_logic()
