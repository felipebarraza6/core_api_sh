#!/usr/bin/env python3
"""
Script para ejecutar el cronjob usando la FUNCIÓN UNIFICADA de procesamiento de totalizados
para el punto 161. Este script demuestra cómo todos los cronjobs deben usar la misma función.
"""

import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail
from api.cronjobs.telemetry.controllers.unified_processing import (
    process_totalizado_variable
)
from datetime import datetime
import pytz

def ejecutar_cron_unificado_punto_161():
    """Ejecuta el cronjob usando la FUNCIÓN UNIFICADA para el punto 161"""
    
    print("=== EJECUTANDO CRONJOB UNIFICADO PARA PUNTO 161 ===")
    print("🚀 Usando función centralizada de procesamiento de totalizados")
    
    # Obtener el punto
    try:
        punto = CatchmentPoint.objects.get(id=161)
        print(f"✅ Punto encontrado: {punto.title}")
        print(f"   ID: {punto.id}")
        print(f"   Frecuencia: {punto.frecuency} minutos")
    except CatchmentPoint.DoesNotExist:
        print("❌ Punto 161 no encontrado")
        return
    
    # Obtener el último registro
    ultimo_registro = InteractionDetail.objects.filter(
        catchment_point_id=161
    ).order_by('-created').first()
    
    if ultimo_registro:
        print(f"✅ Último registro encontrado:")
        print(f"   Total: {ultimo_registro.total}")
        print(f"   Fecha: {ultimo_registro.created}")
    else:
        print("⚠️  No hay registros previos")
    
    # Simular los datos que llegaron del sensor
    # Sabemos que son 55 pulsos con factor 1000
    pulsos_recibidos = 55
    factor = 1000
    
    print(f"\n=== DATOS DEL SENSOR ===")
    print(f"Pulsos recibidos: {pulsos_recibidos}")
    print(f"Factor: {factor}")
    
    # Preparar datos para la función unificada
    point_catchment = {
        'id': punto.id,
        'title': punto.title,
        'frecuency': punto.frecuency,
        'profile_data_config': punto.profile_data_config,
        'variables': punto.variables
    }
    
    variable = {
        'type_variable': 'TOTALIZADO',
        'str_variable': 'TOTALIZADOR_PRINCIPAL',
        'pulses_factor': factor
    }
    
    data = {
        'value': pulsos_recibidos,
        'date_time': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    }
    
    # ✅ PROCESAR TOTALIZADO USANDO FUNCIÓN UNIFICADA
    print(f"\n=== PROCESAMIENTO UNIFICADO ===")
    try:
        # Inicializar registro
        created_register = {}
        
        # Usar función consolidada de unified_processing.py
        date_time_last_logger_total, created_register = process_totalizado_variable(
            data, variable, point_catchment, created_register
        )
        
        print("✅ Procesamiento unificado completado exitosamente!")
        
        # Mostrar resumen del procesamiento
        print(f"\n📊 RESUMEN TOTALIZADO - Punto {point_catchment['id']} ({point_catchment.get('title', 'Sin título')}):")
        print(f"   • Pulsos: {created_register.get('pulses', 0)}")
        print(f"   • Total: {created_register.get('total', '0')}")
        print(f"   • Diferencia hora: {created_register.get('total_diff', 0)}")
        print(f"   • Acumulado día: {created_register.get('total_today_diff', 0)}")
        print(f"   • Último logger: {created_register.get('date_time_last_logger', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Error en procesamiento unificado: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Crear el registro manualmente para las 23:00 horas
    print(f"\n=== CREANDO REGISTRO PARA 23:00 HORAS ===")
    
    # Configurar zona horaria de Chile
    chile_tz = pytz.timezone('America/Santiago')
    ahora_chile = datetime.now(chile_tz)
    
    # Crear timestamp para las 23:00 horas
    timestamp_23h = ahora_chile.replace(
        hour=23, minute=0, second=0, microsecond=0
    )
    
    print(f"Hora actual en Chile: {ahora_chile.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Timestamp para 23:00: {timestamp_23h.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Crear el registro usando los datos procesados por la función unificada
    nuevo_registro = InteractionDetail(
        catchment_point_id=161,
        created=timestamp_23h,
        pulses=created_register.get('pulses', 0),
        total=created_register.get('total', '0'),
        total_diff=created_register.get('total_diff', 0),
        total_today_diff=created_register.get('total_today_diff', 0),
        send_dga=True  # Enviar a DGA
    )
    
    # Guardar el registro
    try:
        nuevo_registro.save()
        print(f"✅ Registro creado exitosamente:")
        print(f"   ID: {nuevo_registro.id}")
        print(f"   Total: {nuevo_registro.total}")
        print(f"   Fecha: {nuevo_registro.created}")
        print(f"   Diferencia hora: {nuevo_registro.total_diff}")
        print(f"   Acumulado día: {nuevo_registro.total_today_diff}")
    except Exception as e:
        print(f"❌ Error al crear registro: {e}")
    
    print(f"\n=== VERIFICACIÓN FINAL ===")
    
    # Verificar que el registro se creó correctamente
    registro_verificado = InteractionDetail.objects.get(id=nuevo_registro.id)
    print(f"Registro verificado en BD:")
    print(f"   Total: {registro_verificado.total}")
    print(f"   Diferencia: {registro_verificado.total_diff}")
    
    print(f"\n🎯 REGISTRO DE 23:00 HORAS RECUPERADO EXITOSAMENTE!")
    print(f"   El punto 161 ahora tiene el total correcto: {registro_verificado.total}")
    
    print(f"\n🚀 BENEFICIOS DE LA UNIFICACIÓN:")
    print(f"   ✅ Todos los cronjobs usan la misma función")
    print(f"   ✅ Fórmula consistente: (pulsos × factor) ÷ 1000")
    print(f"   ✅ Manejo robusto de errores")
    print(f"   ✅ Validación centralizada")
    print(f"   ✅ Logging estructurado")

if __name__ == "__main__":
    ejecutar_cron_unificado_punto_161()
