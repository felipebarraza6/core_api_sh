#!/usr/bin/env python3
"""
🧪 PRUEBA RÁPIDA: total_day() corregido
"""

import os
import sys
import django
from datetime import datetime

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core_api.settings")
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail
from api.cronjobs.telemetry.controllers.total import total_day


def probar_total_day_corregido():
    """Probar la función total_day corregida"""
    
    print("🧪 PRUEBA RÁPIDA: total_day() CORREGIDO")
    print("=" * 50)
    
    # Buscar un punto con datos
    punto = CatchmentPoint.objects.filter(
        is_tdata=True, 
        data_config_profiles__is_telemetry=True
    ).first()
    
    if not punto:
        print("❌ No se encontraron puntos de captación")
        return
    
    print(f"📍 Punto: {punto.id} - {punto.name}")
    
    # Verificar registros del día
    hoy = datetime.now().date()
    registros_hoy = InteractionDetail.objects.filter(
        catchment_point_id=punto.id,
        created__date=hoy
    ).exclude(total__isnull=True).exclude(total="")
    
    print(f"\n📊 Registros del día {hoy}:")
    for reg in registros_hoy.order_by('created')[:5]:  # Solo los primeros 5
        print(f"   {reg.created.strftime('%H:%M')} - Total: {reg.total} m³")
    
    if registros_hoy.count() > 5:
        print(f"   ... y {registros_hoy.count() - 5} más")
    
    # Probar función total_day
    print(f"\n🔍 PROBANDO total_day():")
    
    try:
        # Caso 1: Con current_diff
        resultado_con_diff = total_day(
            {"id": punto.id}, 
            None, 
            100  # Simular current_diff = 100
        )
        print(f"   ✅ Con current_diff=100: {resultado_con_diff} m³")
        
        # Caso 2: Sin current_diff (usar lógica optimizada)
        resultado_sin_diff = total_day(
            {"id": punto.id}, 
            None, 
            None  # Sin current_diff
        )
        print(f"   ✅ Sin current_diff: {resultado_sin_diff} m³")
        
        # Caso 3: Con fecha específica
        resultado_con_fecha = total_day(
            {"id": punto.id}, 
            datetime.now(), 
            None
        )
        print(f"   ✅ Con fecha actual: {resultado_con_fecha} m³")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n🎯 PRUEBA COMPLETADA")


if __name__ == "__main__":
    probar_total_day_corregido()
