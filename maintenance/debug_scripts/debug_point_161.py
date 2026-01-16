#!/usr/bin/env python3
"""
Script para diagnosticar por qué el punto 161 no se agrega a la cola DGA
"""

import os
import sys
import django
from datetime import datetime
import pytz

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail

def debug_point_161():
    """Diagnosticar el punto 161"""
    print("🔍 DIAGNÓSTICO DEL PUNTO 161")
    print("=" * 50)
    
    # 1. Verificar si existe el punto
    point = CatchmentPoint.objects.filter(id=161).first()
    if not point:
        print("❌ Punto 161 NO encontrado en la base de datos")
        return
    
    print(f"✅ Punto 161 encontrado: {point.title}")
    print(f"   - ID: {point.id}")
    print(f"   - Proyecto: {point.project.name if point.project else 'Sin proyecto'}")
    print(f"   - Frecuencia: {point.frecuency}")
    print(f"   - is_thethings: {point.is_thethings}")
    print(f"   - is_tdata: {point.is_tdata}")
    
    # 2. Verificar configuración DGA
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=161).first()
    if not dga_config:
        print("\n❌ NO hay configuración DGA para el punto 161")
        print("   Esto significa que NUNCA se agregará a la cola DGA")
        return
    
    print(f"\n✅ Configuración DGA encontrada:")
    print(f"   - send_dga: {dga_config.send_dga}")
    print(f"   - standard: {dga_config.standard}")
    print(f"   - code_dga: {dga_config.code_dga}")
    print(f"   - type_dga: {dga_config.type_dga}")
    print(f"   - rut_report_dga: {dga_config.rut_report_dga}")
    print(f"   - password_dga_software: {'Configurado' if dga_config.password_dga_software else 'NO configurado'}")
    
    # 3. Verificar registros recientes
    recent_records = InteractionDetail.objects.filter(catchment_point_id=161).order_by('-created')[:10]
    print(f"\n📊 Últimos 10 registros del punto 161:")
    
    if not recent_records:
        print("   ❌ No hay registros para el punto 161")
        return
    
    for record in recent_records:
        print(f"   ID: {record.id}, Fecha: {record.date_time_medition}, send_dga: {record.send_dga}, total_diff: {record.total_diff}")
    
    # 4. Verificar registros pendientes de DGA
    pending_dga = InteractionDetail.objects.filter(catchment_point_id=161, send_dga=True)
    print(f"\n📋 Registros pendientes de DGA para punto 161: {pending_dga.count()}")
    
    # 5. Simular validación de frecuencia
    print(f"\n🕐 Simulación de validación de frecuencia:")
    chile_tz = pytz.timezone("America/Santiago")
    current_time = datetime.now(chile_tz)
    print(f"   Hora actual: {current_time}")
    
    # Función de validación de frecuencia (copiada del código)
    def validate_frequency(point_catchment, current_time):
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
    
    # Simular validación
    point_data = {"id": 161}
    should_send = dga_config.send_dga and validate_frequency(point_data, current_time)
    print(f"   send_dga configurado: {dga_config.send_dga}")
    print(f"   frecuencia válida: {validate_frequency(point_data, current_time)}")
    print(f"   debería enviar: {should_send}")
    
    # 6. Verificar si hay registros que deberían estar en cola pero no están
    print(f"\n🔍 Análisis de registros que deberían estar en cola:")
    recent_without_dga = InteractionDetail.objects.filter(
        catchment_point_id=161,
        send_dga=False,
        date_time_medition__gte=current_time.replace(hour=current_time.hour-24)  # Últimas 24 horas
    )
    
    print(f"   Registros de las últimas 24h sin send_dga=True: {recent_without_dga.count()}")
    
    # 7. Recomendaciones
    print(f"\n💡 RECOMENDACIONES:")
    if not dga_config.send_dga:
        print("   ❌ Habilitar send_dga en la configuración DGA del punto 161")
    
    if not dga_config.password_dga_software:
        print("   ❌ Configurar password_dga_software en la configuración DGA")
    
    if pending_dga.count() == 0:
        print("   ⚠️ No hay registros pendientes de envío a DGA")
        print("   💡 Verificar que los cronjobs de telemetría estén funcionando")
    
    print(f"\n✅ Diagnóstico completado")

if __name__ == "__main__":
    try:
        debug_point_161()
    except Exception as e:
        print(f"❌ Error en diagnóstico: {e}")
        import traceback
        traceback.print_exc()
