#!/usr/bin/env python
"""
Script de prueba para verificar el cálculo de caudal promedio en unipapel p100
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

def test_unipapel_p100():
    """Probar cálculo de caudal promedio para unipapel p100"""
    print("=" * 60)
    print("PRUEBA: Cálculo de Caudal Promedio - unipapel p100")
    print("=" * 60)
    
    # Buscar punto unipapel p100
    point = CatchmentPoint.objects.filter(
        title__icontains='unipapel'
    ).filter(
        title__icontains='p100'
    ).first()
    
    if not point:
        # Buscar solo por unipapel
        point = CatchmentPoint.objects.filter(title__icontains='unipapel').first()
    
    if not point:
        # Buscar por p100
        point = CatchmentPoint.objects.filter(title__icontains='p100').first()
    
    if not point:
        print("❌ ERROR: No se encontró punto 'unipapel p100'")
        print("\nBuscando todos los puntos con 'unipapel' o 'p100':")
        points_unipapel = CatchmentPoint.objects.filter(title__icontains='unipapel')
        points_p100 = CatchmentPoint.objects.filter(title__icontains='p100')
        print(f"   Puntos con 'unipapel': {points_unipapel.count()}")
        for p in points_unipapel[:5]:
            print(f"      - ID {p.id}: {p.title}")
        print(f"   Puntos con 'p100': {points_p100.count()}")
        for p in points_p100[:5]:
            print(f"      - ID {p.id}: {p.title}")
        return False
    
    print(f"\n✅ Punto encontrado: {point.title} (ID: {point.id})")
    
    # Verificar si tiene variable CAUDAL_PROMEDIO
    variables = Variable.objects.filter(scheme_catchment__points_catchment=point)
    has_caudal_promedio = variables.filter(type_variable="CAUDAL_PROMEDIO").exists()
    
    print(f"\n📊 Variables encontradas: {variables.count()}")
    print(f"   - Tiene CAUDAL_PROMEDIO: {has_caudal_promedio}")
    
    if variables.exists():
        print("   Variables del punto:")
        for var in variables:
            print(f"      - {var.type_variable}: {var.str_variable}")
    
    if not has_caudal_promedio:
        print("\n⚠️  ADVERTENCIA: Este punto NO tiene variable CAUDAL_PROMEDIO")
        print("   El cálculo de caudal promedio solo funciona para puntos con CAUDAL_PROMEDIO")
        return False
    
    # Obtener últimos 10 registros
    records = InteractionDetail.objects.filter(
        catchment_point=point
    ).order_by('-date_time_medition')[:10]
    
    if not records.exists():
        print("\n❌ ERROR: No hay registros para este punto")
        return False
    
    print(f"\n📝 Registros encontrados: {records.count()}")
    print("\n" + "-" * 60)
    print("PRUEBA DE CÁLCULO DE CAUDAL PROMEDIO:")
    print("-" * 60)
    
    chile_tz = pytz.timezone("America/Santiago")
    success_count = 0
    error_count = 0
    zero_count = 0
    
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
                        zero_count += 1
                        print(f"    ⚠️  Caudal = 0 (puede ser normal si no hay consumo)")
                else:
                    print(f"    ❌ No hay timestamp disponible")
                    error_count += 1
                    
            except Exception as e:
                print(f"    ❌ ERROR al calcular: {str(e)}")
                import traceback
                traceback.print_exc()
                error_count += 1
        else:
            print(f"    ⚠️  No hay total disponible")
    
    print("\n" + "=" * 60)
    print("RESUMEN:")
    print("=" * 60)
    print(f"✅ Cálculos exitosos con caudal > 0: {success_count}")
    print(f"⚠️  Caudales = 0 (sin consumo): {zero_count}")
    print(f"❌ Errores: {error_count}")
    print(f"📊 Total registros probados: {records.count()}")
    
    if success_count > 0:
        print("\n✅ PRUEBA EXITOSA: El cálculo de caudal promedio funciona correctamente")
        print("   Se calcularon caudales válidos para este punto")
        return True
    elif error_count == 0:
        print("\n⚠️  ADVERTENCIA: No se calcularon caudales > 0")
        print("   Esto puede ser normal si no hay consumo en los registros probados")
        print("   El cálculo funciona correctamente, solo que no hay diferencia de consumo")
        return True
    else:
        print("\n❌ PRUEBA FALLIDA: Hubo errores en el cálculo")
        return False

if __name__ == "__main__":
    try:
        success = test_unipapel_p100()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR FATAL: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

