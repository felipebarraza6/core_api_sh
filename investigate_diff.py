from api.core.models import InteractionDetail
import pytz

# Obtener el registro problemático
r = InteractionDetail.objects.get(id=1716680)
chile = pytz.timezone('America/Santiago')

print("=== REGISTRO ACTUAL (18:00) ===")
print(f"ID: {r.id}")
print(f"Fecha medición: {r.date_time_medition.astimezone(chile) if r.date_time_medition else 'None'}")
print(f"Created: {r.created.astimezone(chile)}")
print(f"Pulses: {r.pulses}")
print(f"Total: {r.total}")
print(f"total_diff: {r.total_diff}")
print(f"Punto: {r.catchment_point_id}")

# Buscar registro anterior por created
prev = InteractionDetail.objects.filter(
    catchment_point=r.catchment_point,
    created__lt=r.created
).order_by('-created').first()

if prev:
    print("\n=== REGISTRO ANTERIOR ===")
    print(f"ID: {prev.id}")
    print(f"Fecha medición: {prev.date_time_medition.astimezone(chile) if prev.date_time_medition else 'None'}")
    print(f"Created: {prev.created.astimezone(chile)}")
    print(f"Pulses: {prev.pulses}")
    print(f"Total: {prev.total}")
    print(f"total_diff: {prev.total_diff}")
    
    print("\n=== ANÁLISIS ===")
    diff_esperado = int(r.total) - int(prev.total)
    print(f"Diferencia de totales: {r.total} - {prev.total} = {diff_esperado}")
    print(f"total_diff almacenado: {r.total_diff}")
    print(f"¿Coincide?: {'✅ SÍ' if diff_esperado == r.total_diff else '❌ NO'}")
    
    # Buscar si hay registros entre medio
    between = InteractionDetail.objects.filter(
        catchment_point=r.catchment_point,
        created__gt=prev.created,
        created__lt=r.created
    ).order_by('created')
    
    if between.exists():
        print(f"\n⚠️ HAY {between.count()} REGISTROS ENTRE MEDIO:")
        for b in between:
            print(f"  ID: {b.id}, Created: {b.created.astimezone(chile)}, Total: {b.total}")
