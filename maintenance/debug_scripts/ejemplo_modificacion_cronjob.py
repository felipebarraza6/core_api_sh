#!/usr/bin/env python3
"""
EJEMPLO DE MODIFICACIÓN DE CRONJOB PARA USAR FUNCIÓN UNIFICADA
===============================================================

Este archivo muestra exactamente cómo modificar cualquier cronjob para que use
la función unificada de procesamiento de totalizados.
"""

# ❌ ANTES: Importaciones con lógica duplicada
"""
from .controllers.total import total_day, total_hour, total_m3
from .controllers.flow import average_flow, instantaneous_flow
from .controllers.nivel import nivel_mt, water_table
"""

# ✅ DESPUÉS: Importaciones con función unificada
"""
from .controllers.unified_total_processing import (
    process_totalized_data_unified,
    validate_totalized_data
)
from .controllers.flow import average_flow, instantaneous_flow
from .controllers.nivel import nivel_mt, water_table
"""

# ❌ ANTES: Lógica duplicada de totalizados (20+ líneas)
"""
elif type_variable == "TOTALIZADO":
    # LÓGICA DUPLICADA - Cada cronjob tiene esto
    try:
        value = int(float(data["value"]))
    except (ValueError, TypeError):
        value = 0
    
    created_register["pulses"] = value
    created_register["total"] = total_m3(
        variable.get("pulses_factor"), value, point_catchment
    )
    created_register["total_diff"] = total_hour(
        created_register["total"], point_catchment
    )
    created_register["total_today_diff"] = total_day(
        created_register["total"], point_catchment
    )
    created_register["date_time_last_logger"] = data["date_time"]
    date_time_last_logger_total = data["date_time"]
    
    log_variable_processing(
        point_catchment["id"],
        variable.get("str_variable"),
        "TOTALIZADO",
        True,
    )
"""

# ✅ DESPUÉS: Función unificada (3 líneas)
"""
elif type_variable == "TOTALIZADO":
    # FUNCIÓN UNIFICADA - Todos los cronjobs usan esto
    created_register, date_time_last_logger_total = (
        process_totalized_data_unified(
            point_catchment, variable, data, current_timestamp, chile_tz
        )
    )
"""

# 🔧 CAMBIOS NECESARIOS EN LA FUNCIÓN PRINCIPAL

def get_data_twin_unified(variables, token, point_catchment):
    """Get data by father twin - UNIFICADO COMPLETAMENTE"""
    
    # ✅ 1. AGREGAR VARIABLES NECESARIAS
    chile_tz = pytz.timezone("America/Santiago")
    created_register = {}
    date_time_last_logger_total = None
    
    # ✅ 2. TIMESTAMP ACTUAL PARA CÁLCULOS
    created_register["date_time_medition"] = datetime.now(chile_tz).strftime(
        "%Y-%m-%dT%H:%M:00"
    )
    
    # ✅ 3. ITERAR SOBRE VARIABLES
    for variable in variables:
        data = None
        
        # Obtener datos según servicio...
        if variable.get("token_service"):
            if variable.get("service") == "TWIN":
                data = get_data_with_retry(
                    get_data_tdata, token_twin, variable.get("str_variable")
                )
            # ... otros servicios
        
        # ✅ 4. MANEJAR DATOS FALTANTES
        if data is None:
            if variable.get("type_variable") == "TOTALIZADO":
                data = {"value": 0, "date_time": None}
            else:
                data = {"value": 0.00, "date_time": None}
        
        # ✅ 5. PROCESAR VARIABLE SEGÚN TIPO
        try:
            if variable.get("type_variable") == "TOTALIZADO":
                # ✅ FUNCIÓN UNIFICADA - 3 líneas en lugar de 20+
                current_timestamp = datetime.strptime(
                    data["date_time"], "%Y-%m-%dT%H:%M:%S"
                ) if data.get("date_time") else datetime.now(chile_tz)
                
                created_register, date_time_last_logger_total = (
                    process_totalized_data_unified(
                        point_catchment, variable, data, current_timestamp, chile_tz
                    )
                )
                
            elif variable.get("type_variable") == "NIVEL":
                # Mantener lógica existente para nivel
                created_register = process_nivel_variable(
                    data, variable, point_catchment, created_register
                )
                
            elif variable.get("type_variable") == "CAUDAL":
                # Mantener lógica existente para caudal
                created_register = process_caudal_variable(
                    data, variable, point_catchment, created_register
                )
                
            elif variable.get("type_variable") == "CAUDAL_PROMEDIO":
                # Mantener lógica existente para caudal promedio
                created_register = process_caudal_promedio_variable(
                    date_time_last_logger_total, created_register, point_catchment
                )
                
        except Exception as e:
            log_variable_processing(
                point_catchment["id"],
                variable.get("str_variable"),
                variable.get("type_variable"),
                False,
                str(e),
            )
    
    # ✅ 6. CALCULAR DÍAS SIN CONEXIÓN
    if created_register.get("date_time_last_logger"):
        date_time_medition = datetime.strptime(
            created_register["date_time_medition"], "%Y-%m-%dT%H:00:00"
        )
        date_time_last_logger = datetime.strptime(
            created_register["date_time_last_logger"], "%Y-%m-%dT%H:%M:%S"
        )
        days_not_conection = (date_time_medition - date_time_last_logger).days
        if days_not_conection < 0:
            days_not_conection = 0
        created_register["days_not_conection"] = days_not_conection
    
    # ✅ 7. DETERMINAR ENVÍO A DGA
    get = DgaDataConfigCatchment.objects.get(
        point_catchment__id=point_catchment["id"]
    )
    current_time = datetime.now(chile_tz)
    
    if get.send_dga and validate_frequency(point_catchment, current_time):
        created_register["send_dga"] = True
    else:
        created_register["send_dga"] = False
    
    # ✅ 8. CREAR REGISTRO EN BD
    InteractionDetail.objects.create(
        catchment_point_id=point_catchment["id"], **created_register
    )

# 📊 COMPARACIÓN DE LÍNEAS DE CÓDIGO

"""
❌ ANTES (lógica duplicada):
- twin.py: ~348 líneas
- twin_f1.py: ~341 líneas  
- twin_f5.py: ~340 líneas
- nettra.py: ~330 líneas
- novus.py: ~328 líneas
- nettra_f5.py: ~328 líneas

✅ DESPUÉS (función unificada):
- Todos los cronjobs: ~280-300 líneas
- Lógica de totalizados: 3 líneas (en lugar de 20+)
- Código duplicado: ELIMINADO COMPLETAMENTE
"""

# 🎯 BENEFICIOS INMEDIATOS

"""
1. 🔒 CONFIABILIDAD:
   - Todos los cronjobs usan exactamente la misma lógica
   - Fórmula consistente: (pulsos × factor) ÷ 1000
   - Manejo uniforme de errores

2. 🛠️ MANTENIMIENTO:
   - Un solo lugar para actualizar lógica de totalizados
   - Código duplicado eliminado
   - Debugging centralizado

3. 📊 CALIDAD:
   - Validación centralizada
   - Protección uniforme contra valores negativos
   - Logging estructurado
"""

# 🚀 PRÓXIMOS PASOS

"""
1. ✅ Crear función unificada (COMPLETADO)
2. ⏳ Modificar twin.py para usar función unificada
3. ⏳ Modificar twin_f1.py para usar función unificada
4. ⏳ Modificar twin_f5.py para usar función unificada
5. ⏳ Modificar nettra.py para usar función unificada
6. ⏳ Modificar novus.py para usar función unificada
7. ⏳ Modificar nettra_f5.py para usar función unificada
8. ⏳ Probar todos los cronjobs modificados
9. ⏳ Verificar consistencia de resultados
"""

print("✅ Ejemplo de modificación de cronjob completado!")
print("🚀 Ahora puedes aplicar estos cambios a todos tus cronjobs")
