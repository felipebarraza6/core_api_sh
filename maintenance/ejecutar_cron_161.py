#!/usr/bin/env python3
"""
Script para ejecutar el cronjob twin.py SOLO para el punto 161
"""

import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.core.models import CatchmentPoint
from api.cronjobs.telemetry.twin import get_data_twin

def ejecutar_cron_161():
    """Ejecuta el cronjob twin.py solo para el punto 161"""
    
    print("=== EJECUTANDO CRONJOB TWIN.PY PARA PUNTO 161 ===")
    
    # Obtener solo el punto 161
    try:
        punto = CatchmentPoint.objects.get(id=161)
        print(f"✅ Punto: {punto.title} (ID: {punto.id})")
        print(f"   Frecuencia: {punto.frecuency} minutos")
    except CatchmentPoint.DoesNotExist:
        print("❌ Punto 161 no encontrado")
        return
    
    # Convertir a diccionario como espera la función
    point_data = {
        'id': punto.id,
        'title': punto.title,
        'frecuency': punto.frecuency,
        'profile_data_config': punto.profile_data_config,
        'variables': punto.variables
    }
    
    print(f"\n🚀 Ejecutando get_data_twin para punto 161...")
    
    # Ejecutar la función del cronjob
    try:
        resultado = get_data_twin(point_data)
        print(f"✅ Cronjob ejecutado exitosamente!")
        print(f"Resultado: {resultado}")
    except Exception as e:
        print(f"❌ Error ejecutando cronjob: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    ejecutar_cron_161()
