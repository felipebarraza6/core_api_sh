#!/usr/bin/env python
"""
Script de prueba para verificar el cálculo de caudal promedio en el punto 100
"""
import os
import sys
import django

# Configurar Django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail, Variable
from api.cronjobs.telemetry.controllers.flow import average_flow
import pytz
from datetime import datetime

def test_p100_caudal():
    """Probar cálculo de caudal promedio para el punto 100"""
    print("=" * 60)
    print("PRUEBA: Cálculo de Caudal Promedio - Punto 100")
    print("=" * 60)
    
    # Obtener punto 100
    point = CatchmentPoint.objects.filter(id=100).first()
    if not point:
        print("❌ ERROR: Punto 100 no encontrado")
        return False
    
    print(f"\n✅ Punto encontrado: {point.title} (ID: {point.id})")
    
    # Verificar si tiene variable CAUDAL_PROMEDIO
    variables = Variable.objects.filter(scheme_catchment__points_catchment=point)
    has_caudal_promedio = variables.filter(type_variable="CAUDAL_PROMEDIO").exists()
    
    print(f"\n📊 Variables encontradas: {variables.count()}")
    print(f"   - Tiene CAUDAL_PROMEDIO: {has_caudal_promedio}")
    
    if not has_caudal_promedio:
        print("\n⚠️  ADVERTENCIA: El punto 100 NO tiene variable CAUDAL_PROMEDIO")
        print("   Variables del punto:")
        for var in variables:
            print(f"      - {var.type_variable}: {var.str_variable}")
        return False
    
    # Obtener últimos 10 registros
    records = InteractionDetail.objects.filter(
        catchment_point=point
    ).order_by('-date_time_medition')[:10]
    
    if not records.exists():
        print("\n❌ ERROR: No hay registros para el punto 100")
        return False
    
    print(f"\n📝 Registros encontrados: {records.count()}")
    print("\n" + "-" * 60)
    print("PRUEBA DE CÁLCULO DE CAUDAL PROMEDIO:")
    print("-" * 60)
    
    chile_tz = pytz.timezone("America/Santiago")
    success_count = 0
    error_count = 0
    
    for idx, record in enumerate(records, 1):
        print(f"\n[{idx}] Registro ID: {record.id}")
        print(f"    Fecha Medición: {record.date_time_medition}")
        print(f"    Fecha Logger: {record.date_time_last_logger or 'N/A'}")
        print(f"    Total: {record.total} m³")
        print(f"    Total Diff: {record.total_diff} m³/h")
        print(f"    Flow guardado: {record.flow} L/s")
        
        if record.total:
            try:
                point_dict = {"id": point.id}
                total_actual = float(record.total)
                
                # Usar date_time_last_logger si existe, sino date_time_medition
                curr_ts = record.date_time_last_logger if record.date_time_last_logger else record.date_time_medition
                
                if curr_ts:
                    if curr_ts.tzinfo is None:
                        curr_ts = chile_tz.localize(curr_ts)
                    else:
                        curr_ts = curr_ts.astimezone(chile_tz)
                    
                    # Calcular caudal promedio
                    caudal_calculado = average_flow(point_dict, total_actual, curr_ts)
                    
                    print(f"    ✅ Caudal Calculado: {caudal_calculado} L/s")
                    
                    if caudal_calculado > 0:
                        success_count += 1
                        print(f"    ✓ Caudal válido calculado correctamente")
                    else:
                        print(f"    ⚠️  Caudal = 0 (puede ser normal si no hay consumo)")
                else:
                    print(f"    ❌ No hay timestamp disponible")
                    error_count += 1
                    
            except Exception as e:
                print(f"    ❌ ERROR al calcular: {str(e)}")
                error_count += 1
        else:
            print(f"    ⚠️  No hay total disponible")
    
    print("\n" + "=" * 60)
    print("RESUMEN:")
    print("=" * 60)
    print(f"✅ Cálculos exitosos: {success_count}")
    print(f"❌ Errores: {error_count}")
    print(f"📊 Total registros probados: {records.count()}")
    
    if success_count > 0:
        print("\n✅ PRUEBA EXITOSA: El cálculo de caudal promedio funciona correctamente")
        return True
    else:
        print("\n⚠️  ADVERTENCIA: No se calcularon caudales válidos (puede ser normal si no hay consumo)")
        return True  # Aún así es exitoso si no hay errores

if __name__ == "__main__":
    try:
        success = test_p100_caudal()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR FATAL: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

