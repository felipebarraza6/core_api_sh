#!/usr/bin/env python3
"""
Script para diagnosticar el punto 161
"""

import os
import django
from datetime import datetime
import pytz

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail

def debug_point_161():
    print("🔍 DIAGNÓSTICO DEL PUNTO 161")
    print("=" * 50)
    
    # Configuración del punto
    point = CatchmentPoint.objects.filter(id=161).first()
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=161).first()
    
    print(f"Punto: {point.title}")
    print(f"Config DGA: send_dga={dga_config.send_dga}, standard={dga_config.standard}")
    
    # Hora actual
    chile_tz = pytz.timezone("America/Santiago")
    current_time = datetime.now(chile_tz)
    print(f"Hora actual: {current_time}")
    
    # Verificar horas anteriores
    print("\nVerificando horas anteriores:")
    for hour in [14, 15, 16, 17, 18, 19]:
        check_time = current_time.replace(hour=hour, minute=0, second=0, microsecond=0)
        should_send = dga_config.send_dga and (check_time.minute == 0)
        print(f"  {hour}:00 - ¿Debería enviar?: {should_send}")
    
    # Verificar registros de las últimas horas
    print("\nRegistros de las últimas horas:")
    recent_records = InteractionDetail.objects.filter(
        catchment_point_id=161
    ).order_by('-created')[:10]
    
    for record in recent_records:
        print(f"  ID: {record.id}, Fecha: {record.date_time_medition}, send_dga: {record.send_dga}, total_diff: {record.total_diff}")
    
    # Verificar si hay registros pendientes
    pending = InteractionDetail.objects.filter(catchment_point_id=161, send_dga=True).count()
    print(f"\nRegistros pendientes de DGA: {pending}")
    
    # Verificar registros con consumo
    with_consumption = InteractionDetail.objects.filter(catchment_point_id=161, total_diff__gt=0).count()
    print(f"Registros con consumo (total_diff > 0): {with_consumption}")

if __name__ == "__main__":
    debug_point_161()
