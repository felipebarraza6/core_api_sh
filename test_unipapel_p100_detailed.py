#!/usr/bin/env python
"""
Script de prueba detallado para verificar el cálculo de caudal promedio en unipapel p100
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

def test_unipapel_p100_detailed():
    """Probar cálculo de caudal promedio para unipapel p100 con más detalle"""
    print("=" * 60)
    print("PRUEBA DETALLADA: Cálculo de Caudal Promedio - unipapel p100")
    print("=" * 60)
    
    # Buscar punto P100
    point = CatchmentPoint.objects.filter(id=14).first()
    
    if not point:
        print("❌ ERROR: No se encontró punto ID 14")
        return False
    
    print(f"\n✅ Punto encontrado: {point.title} (ID: {point.id})")
    
    # Verificar si tiene variable CAUDAL_PROMEDIO
    variables = Variable.objects.filter(scheme_catchment__points_catchment=point)
    has_caudal_promedio = variables.filter(type_variable="CAUDAL_PROMEDIO").exists()
    
    if not has_caudal_promedio:
        print("\n❌ ERROR: Este punto NO tiene variable CAUDAL_PROMEDIO")
        return False
    
    # Obtener registros ordenados por fecha
    records = InteractionDetail.objects.filter(
        catchment_point=point
    ).order_by('date_time_medition')[:20]
    
    if records.count() < 2:
        print("\n❌ ERROR: Se necesitan al menos 2 registros para calcular caudal")
        return False
    
    print(f"\n📝 Registros encontrados: {records.count()}")
    print("\n" + "-" * 60)
    print("ANÁLISIS DETALLADO:")
    print("-" * 60)
    
    chile_tz = pytz.timezone("America/Santiago")
    
    # Probar con el segundo registro en adelante (necesitamos uno anterior)
    for idx in range(1, min(10, records.count())):
        record = records[idx]
        prev_record = records[idx - 1]
        
        print(f"\n[{idx}] Registro ID: {record.id}")
        print(f"    Fecha Medición: {record.date_time_medition}")
        print(f"    Fecha Logger: {record.date_time_last_logger or 'N/A'}")
        print(f"    Total: {record.total} m³")
        print(f"    Total Diff: {record.total_diff} m³/h")
        
        print(f"\n    Registro Anterior ID: {prev_record.id}")
        print(f"    Fecha Medición Anterior: {prev_record.date_time_medition}")
        print(f"    Fecha Logger Anterior: {prev_record.date_time_last_logger or 'N/A'}")
        print(f"    Total Anterior: {prev_record.total} m³")
        
        if record.total and prev_record.total:
            try:
                # Calcular diferencia manualmente
                total_diff = float(record.total) - float(prev_record.total)
                print(f"    Diferencia Total: {total_diff} m³")
                
                # Calcular diferencia de tiempo
                curr_ts = record.date_time_last_logger if record.date_time_last_logger else record.date_time_medition
                prev_ts = prev_record.date_time_last_logger if prev_record.date_time_last_logger else prev_record.date_time_medition
                
                if curr_ts and prev_ts:
                    if curr_ts.tzinfo is None:
                        curr_ts = chile_tz.localize(curr_ts)
                    else:
                        curr_ts = curr_ts.astimezone(chile_tz)
                    
                    if prev_ts.tzinfo is None:
                        prev_ts = chile_tz.localize(prev_ts)
                    else:
                        prev_ts = prev_ts.astimezone(chile_tz)
                    
                    time_diff = (curr_ts - prev_ts).total_seconds()
                    print(f"    Diferencia Tiempo: {time_diff} segundos ({time_diff/3600:.2f} horas)")
                    
                    if time_diff > 0 and total_diff > 0:
                        caudal_manual = (total_diff / time_diff) * 1000.0
                        print(f"    Caudal Manual: {caudal_manual:.2f} L/s")
                    
                    # Probar con average_flow
                    point_dict = {"id": point.id}
                    total_actual = float(record.total)
                    caudal_calculado = average_flow(point_dict, total_actual, curr_ts)
                    print(f"    ✅ Caudal Calculado (average_flow): {caudal_calculado} L/s")
                    
                    if caudal_calculado > 0:
                        print(f"    ✓ Caudal válido calculado correctamente")
                    else:
                        print(f"    ⚠️  Caudal = 0")
                else:
                    print(f"    ❌ No hay timestamps disponibles")
                    
            except Exception as e:
                print(f"    ❌ ERROR: {str(e)}")
                import traceback
                traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("FIN DEL ANÁLISIS")
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        test_unipapel_p100_detailed()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ ERROR FATAL: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

