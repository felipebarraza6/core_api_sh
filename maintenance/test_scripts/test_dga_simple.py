from api.core.models import InteractionDetail, Variable
from api.cronjobs.dga.cron_dga import _has_average_flow_variable, _calculate_dynamic_flow

# Probar punto P100 (ID: 14)
point_id = 14
print(f"=== Probando punto {point_id} ===")

# 1. Verificar CAUDAL_PROMEDIO
has_caudal_promedio = _has_average_flow_variable(point_id)
print(f"¿Tiene CAUDAL_PROMEDIO? {has_caudal_promedio}")

# 2. Obtener último registro
last_register = InteractionDetail.objects.filter(
    catchment_point_id=point_id
).order_by('-date_time_medition').first()

if last_register:
    print(f"Último registro: {last_register.date_time_medition}")
    print(f"Flow guardado: {last_register.flow}")
    print(f"Total guardado: {last_register.total}")
    
    # 3. Calcular caudal dinámico
    if has_caudal_promedio:
        dynamic_flow = _calculate_dynamic_flow(last_register)
        print(f"Caudal dinámico calculado: {dynamic_flow}")
else:
    print("No hay registros para este punto")
