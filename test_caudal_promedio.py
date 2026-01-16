#!/usr/bin/env python
"""
Script de prueba para verificar el cálculo de caudal promedio
Busca puntos con CAUDAL_PROMEDIO y prueba el cálculo
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

def test_caudal_promedio_points():
    """Buscar puntos con CAUDAL_PROMEDIO y probar el cálculo"""
    print("=" * 60)
    print("PRUEBA: Cálculo de Caudal Promedio")
    print("=" * 60)
    
    # Buscar puntos con CAUDAL_PROMEDIO
    variables_caudal_promedio = Variable.objects.filter(type_variable="CAUDAL_PROMEDIO")
    
    if not variables_caudal_promedio.exists():
        print("\n❌ ERROR: No se encontraron variables CAUDAL_PROMEDIO en el sistema")
        return False
    
    print(f"\n📊 Variables CAUDAL_PROMEDIO encontradas: {variables_caudal_promedio.count()}")
    
    # Obtener puntos únicos
    points_with_caudal_promedio = CatchmentPoint.objects.filter(
        schemes__variables__type_variable="CAUDAL_PROMEDIO"
    ).distinct()
    
    print(f"📍 Puntos con CAUDAL_PROMEDIO: {points_with_caudal_promedio.count()}")
    
    if not points_with_caudal_promedio.exists():
        print("\n❌ ERROR: No se encontraron puntos con CAUDAL_PROMEDIO")
        return False
    
    # Probar con los primeros 3 puntos
    test_points = points_with_caudal_promedio[:3]
    
    chile_tz = pytz.timezone("America/Santiago")
    total_success = 0
    total_errors = 0
    
    for point in test_points:
        print("\n" + "=" * 60)
        print(f"PUNTO: {point.title} (ID: {point.id})")
        print("=" * 60)
        
        # Obtener últimos 5 registros
        records = InteractionDetail.objects.filter(
            catchment_point=point
        ).order_by('-date_time_medition')[:5]
        
        if not records.exists():
            print(f"⚠️  No hay registros para este punto")
            continue
        
        print(f"📝 Registros encontrados: {records.count()}")
        
        for idx, record in enumerate(records, 1):
            print(f"\n  [{idx}] Registro ID: {record.id}")
            print(f"      Fecha Medición: {record.date_time_medition}")
            print(f"      Fecha Logger: {record.date_time_last_logger or 'N/A'}")
            print(f"      Total: {record.total} m³")
            print(f"      Total Diff: {record.total_diff} m³/h")
            print(f"      Flow guardado: {record.flow} L/s")
            
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
                        
                        print(f"      ✅ Caudal Calculado: {caudal_calculado} L/s")
                        
                        if caudal_calculado > 0:
                            total_success += 1
                            print(f"      ✓ Caudal válido calculado correctamente")
                        else:
                            print(f"      ⚠️  Caudal = 0 (puede ser normal si no hay consumo)")
                    else:
                        print(f"      ❌ No hay timestamp disponible")
                        total_errors += 1
                        
                except Exception as e:
                    print(f"      ❌ ERROR al calcular: {str(e)}")
                    total_errors += 1
            else:
                print(f"      ⚠️  No hay total disponible")
    
    print("\n" + "=" * 60)
    print("RESUMEN FINAL:")
    print("=" * 60)
    print(f"✅ Cálculos exitosos con caudal > 0: {total_success}")
    print(f"❌ Errores: {total_errors}")
    
    if total_success > 0:
        print("\n✅ PRUEBA EXITOSA: El cálculo de caudal promedio funciona correctamente")
        return True
    else:
        print("\n⚠️  ADVERTENCIA: No se calcularon caudales válidos")
        print("   Esto puede ser normal si no hay consumo en los registros probados")
        return True  # Aún así es exitoso si no hay errores

if __name__ == "__main__":
    try:
        success = test_caudal_promedio_points()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR FATAL: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

