#!/usr/bin/env python3
"""
Script para probar el cálculo dinámico de caudal promedio en DGA
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
sys.path.append('/root/core_api_sh')
django.setup()

from api.core.models import InteractionDetail
from api.cronjobs.dga.cron_dga import _has_average_flow_variable, _calculate_dynamic_flow

def test_unipapel_points():
    """Probar los puntos de Unipapel"""
    unipapel_points = [14, 15, 16]  # P100, P200, C9
    
    for point_id in unipapel_points:
        print(f"\n=== Probando punto {point_id} ===")
        
        # 1. Verificar si tiene variable CAUDAL_PROMEDIO
        has_caudal_promedio = _has_average_flow_variable(point_id)
        print(f"¿Tiene CAUDAL_PROMEDIO? {has_caudal_promedio}")
        
        # 2. Obtener último registro
        last_register = InteractionDetail.objects.filter(
            catchment_point_id=point_id
        ).order_by('-date_time_medition').first()
        
        if last_register:
            print(f"Último registro: {last_register.date_time_medition}")
            print(f"Flow guardado: {last_register.flow}")
            print(f"Total guardado: {last_register.total}")
            
            # 3. Calcular caudal dinámico
            if has_caudal_promedio:
                dynamic_flow = _calculate_dynamic_flow(last_register)
                print(f"Caudal dinámico calculado: {dynamic_flow}")
        else:
            print("No hay registros para este punto")

if __name__ == "__main__":
    test_unipapel_points()
