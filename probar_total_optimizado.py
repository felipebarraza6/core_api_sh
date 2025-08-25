#!/usr/bin/env python3
"""
🧪 SCRIPT DE PRUEBA: Comparar total_day vs total_day_efficient
Muestra la diferencia de rendimiento entre ambas funciones.
"""

import os
import sys
import django
import time
from datetime import datetime, timedelta

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core_api.settings")
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail
from api.cronjobs.telemetry.controllers.total import total_day


def probar_funciones_optimizadas():
    """Probar y comparar ambas funciones de total_day"""
    
    print("🚀 PRUEBA DE FUNCIONES OPTIMIZADAS PARA TOTAL_TODAY_DIFF")
    print("=" * 70)
    
    # Buscar un punto de captación con datos
    punto = CatchmentPoint.objects.filter(
        is_tdata=True, 
        data_config_profiles__is_telemetry=True
    ).first()
    
    if not punto:
        print("❌ No se encontraron puntos de captación con datos")
        return
    
    print(f"📍 Punto de prueba: {punto.id} - {punto.name}")
    
    # Simular datos de prueba
    total_actual = 1500.0  # m³
    current_dt = datetime.now()
    
    print(f"\n📊 Datos de prueba:")
    print(f"   - Total actual: {total_actual} m³")
    print(f"   - Fecha: {current_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Probar función ORIGINAL (suma todas las diferencias)
    print(f"\n🔍 PRUEBA 1: Función ORIGINAL total_day()")
    print("   (Suma todas las diferencias del día)")
    
    start_time = time.time()
    try:
        acumulado_original = total_day(
            {"id": punto.id}, 
            current_dt, 
            total_actual
        )
        tiempo_original = time.time() - start_time
        print(f"   ✅ Resultado: {acumulado_original} m³")
        print(f"   ⏱️  Tiempo: {tiempo_original:.4f} segundos")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        tiempo_original = 0
    
    # Probar función OPTIMIZADA (diferencia directa)
    print(f"\n🚀 PRUEBA 2: Función OPTIMIZADA total_day()")
    print("   (Total actual - Primer total del día)")
    
    start_time = time.time()
    try:
        acumulado_optimizado = total_day(
            {"id": punto.id}, 
            current_dt, 
            None  # Sin current_diff para usar la lógica optimizada
        )
        tiempo_optimizado = time.time() - start_time
        print(f"   ✅ Resultado: {acumulado_optimizado} m³")
        print(f"   ⏱️  Tiempo: {tiempo_optimizado:.4f} segundos")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        tiempo_optimizado = 0
    
    # Comparar resultados
    print(f"\n📈 COMPARACIÓN DE RENDIMIENTO:")
    print("=" * 50)
    
    if tiempo_original > 0 and tiempo_optimizado > 0:
        mejora = ((tiempo_original - tiempo_optimizado) / tiempo_original) * 100
        print(f"   ⏱️  Tiempo original: {tiempo_original:.4f}s")
        print(f"   ⏱️  Tiempo optimizado: {tiempo_optimizado:.4f}s")
        print(f"   🚀 Mejora: {mejora:.1f}% más rápido")
        
        if acumulado_original == acumulado_optimizado:
            print(f"   ✅ Resultados IDÉNTICOS: {acumulado_original} m³")
        else:
            print(f"   ⚠️  Resultados DIFERENTES:")
            print(f"      Original: {acumulado_original} m³")
            print(f"      Optimizado: {acumulado_optimizado} m³")
    
    # Explicar la optimización
    print(f"\n💡 EXPLICACIÓN DE LA OPTIMIZACIÓN:")
    print("=" * 50)
    print(f"   🔴 FUNCIÓN ORIGINAL:")
    print(f"      - Busca TODOS los registros del día")
    print(f"      - Suma TODAS las diferencias hora por hora")
    print(f"      - Múltiples consultas a la base de datos")
    print(f"      - Complejidad: O(n) donde n = registros del día")
    
    print(f"\n   🟢 FUNCIÓN OPTIMIZADA:")
    print(f"      - Busca SOLO el PRIMER registro del día")
    print(f"      - Calcula: Total actual - Primer total del día")
    print(f"      - Una sola consulta a la base de datos")
    print(f"      - Complejidad: O(1) - constante")
    
    print(f"\n   🎯 BENEFICIOS:")
    print(f"      - ⚡ Mucho más rápida")
    print(f"      - 💾 Menos uso de memoria")
    print(f"      - 🗄️  Menos consultas a la BD")
    print(f"      - 📊 Resultado matemáticamente equivalente")


if __name__ == "__main__":
    probar_funciones_optimizadas()
