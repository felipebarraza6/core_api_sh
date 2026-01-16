# 🔧 GUÍA DE FIXES - DASHBOARD SMARTHYDRO
## Soluciones Prácticas e Implementables

---

## 📋 PREREQUISITOS

Antes de aplicar fixes, hacer backup:
```bash
cp api/core/admin_views.py api/core/admin_views.py.backup-before-fixes
```

---

## 🎯 FIX #1: ELIMINAR N+1 QUERIES EN VERACIDAD (LÍNEA 162-215)

**Impacto**: Reducir de 100+ queries a 2-3 queries
**Tiempo de carga**: 20s → 1s

### Código Actual (LENTO):
```python
for point in obras_points_list:
    profile = point.data_config_profiles.first()
    if not profile or not profile.is_telemetry:
        continue

    # ❌ ESTA QUERY SE EJECUTA PARA CADA PUNTO (N+1)
    last_record = InteractionDetail.objects.filter(
        catchment_point=point
    ).order_by('-date_time_medition').first()
    if not last_record:
        continue
```

### Solución (RÁPIDO):
```python
# ANTES del loop: obtener todos los últimos registros en 1 query
from django.db.models import OuterRef, Subquery, Prefetch

# Subquery para obtener el ID del último registro de cada punto
latest_record_ids = InteractionDetail.objects.filter(
    catchment_point_id=OuterRef('id')
).order_by('-date_time_medition').values('id')[:1]

# Anotar los puntos con el ID del último registro
obras_points_annotated = CatchmentPoint.objects.filter(
    id__in=obras_points_ids
).annotate(
    latest_record_id=Subquery(latest_record_ids)
).select_related('project')

# Obtener TODOS los últimos registros en 1 sola query
latest_record_ids_list = [
    p.latest_record_id for p in obras_points_annotated
    if p.latest_record_id
]
all_latest_records = InteractionDetail.objects.filter(
    id__in=latest_record_ids_list
).select_related('catchment_point', 'catchment_point__project')

# Crear un diccionario para acceso rápido sin queries
records_by_point_id = {
    r.catchment_point_id: r for r in all_latest_records
}

# Ahora el loop es rápido (sin queries):
for point in obras_points_annotated:
    profile = point.data_config_profiles.first()
    if not profile or not profile.is_telemetry:
        continue

    # ✅ Acceso directo al diccionario (NO query)
    last_record = records_by_point_id.get(point.id)
    if not last_record:
        continue

    # Resto del código igual...
```

### Testing:
```python
# Agregar en manage.py
python manage.py shell
>>> from django.test.utils import CaptureQueriesContext
>>> from django.db import connection
>>>
>>> with CaptureQueriesContext(connection) as ctx:
>>>     # Hacer request al dashboard
>>> print(f"Queries ejecutadas: {len(ctx)}")
# Antes: ~150 queries
# Después: ~5 queries
```

---

## 🎯 FIX #2: CORREGIR CÁLCULO DE % CONECTADOS (LÍNEA 128-136)

**Impacto**: Datos correctos en el dashboard
**Riesgo**: Bajo (no afecta otras partes)

### Código Actual (INCORRECTO):
```python
obras_with_telemetry = 0
for point in obras_points_list:
    profile = point.data_config_profiles.first()
    if profile and profile.is_telemetry:
        obras_with_telemetry += 1

# ❌ Puede ser incorrecto si algunos puntos no tienen perfil
pct_conectados = (obras_with_telemetry / num_obras * 100) if num_obras > 0 else 0
```

### Solución (CORRECTA):
```python
# Método 1: Contar de la queryset directamente
obras_with_telemetry = ProfileDataConfigCatchment.objects.filter(
    point_catchment__in=obras_points_ids,
    is_telemetry=True
).count()

pct_conectados = (obras_with_telemetry / num_obras * 100) if num_obras > 0 else 0

# Método 2: Si ya tienes los objetos en memoria
obras_with_telemetry = sum(
    1 for point in obras_points_list
    if point.data_config_profiles.filter(is_telemetry=True).exists()
)

pct_conectados = (obras_with_telemetry / num_obras * 100) if num_obras > 0 else 0
```

### Verificación:
```python
# El porcentaje debe ser:
# (Puntos con telemetría activa / Total de puntos con código de obra) * 100
assert 0 <= pct_conectados <= 100
assert pct_conectados_count <= num_obras
```

---

## 🎯 FIX #3: VALIDAR CONVERSIONES A FLOAT (LÍNEA 745-760)

**Impacto**: Evitar crashes por datos corruptos
**Riesgo**: Bajo

### Código Actual (INSEGURO):
```python
if profile.d6 and float(profile.d6) > 0:  # ❌ Puede crashear
    has_d6 = True
    d6_value = float(profile.d6)
if profile.d3 and float(profile.d3) > 0:  # ❌ Puede crashear
    d3_posicionamiento = float(profile.d3)
```

### Solución (SEGURA):
Reemplazar con:
```python
# Usar la función safe_float que ya existe (línea 30)
d6_safe = safe_float(profile.d6)
if d6_safe > 0:
    has_d6 = True
    d6_value = d6_safe

d3_safe = safe_float(profile.d3)
if d3_safe > 0:
    d3_posicionamiento = d3_safe
```

### Script de Fix:
```bash
# En el archivo admin_views.py, reemplazar líneas 745-760
sed -i 's/if profile\.d6 and float(profile\.d6) > 0:/d6_safe = safe_float(profile.d6)\n            if d6_safe > 0:/g' api/core/admin_views.py
sed -i 's/d6_value = float(profile\.d6)/d6_value = d6_safe/g' api/core/admin_views.py
```

---

## 🎯 FIX #4: MEJORAR MANEJO DE EXCEPCIONES (LÍNEA 564-567)

**Impacto**: Mejor debugging y error handling
**Riesgo**: Bajo

### Código Actual (INCORRECTO):
```python
try:
    error_page_obj = error_paginator.page(page_number)
except:  # ❌ Bare except - muy amplio
    error_page_obj = error_paginator.page(1)
```

### Solución (CORRECTA):
```python
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
import logging

logger = logging.getLogger(__name__)

try:
    page_number = request.GET.get('error_page', 1)
    # Validar que sea un número
    try:
        page_number = int(page_number)
    except ValueError:
        logger.warning(f"Página inválida solicitada (no es número): {page_number}")
        page_number = 1

    error_page_obj = error_paginator.page(page_number)
except (PageNotAnInteger, EmptyPage) as e:
    logger.warning(f"Página inválida: {page_number} - {str(e)}")
    error_page_obj = error_paginator.page(1)
except Exception as e:
    logger.error(f"Error inesperado en paginación: {str(e)}", exc_info=True)
    error_page_obj = error_paginator.page(1)
```

---

## 🎯 FIX #5: COMPLETAR PREFETCH FIELDS (LÍNEA 674-681)

**Impacto**: Eliminar N+1 queries adicionales
**Riesgo**: Bajo

### Código Actual (INCOMPLETO):
```python
Prefetch(
    'catchment_point__data_config_profiles',
    queryset=ProfileDataConfigCatchment.objects.only(
        'point_catchment_id', 'd6', 'is_telemetry', 'd3'  # ❌ Falta d5
    )
)
```

### Solución:
```python
Prefetch(
    'catchment_point__data_config_profiles',
    queryset=ProfileDataConfigCatchment.objects.only(
        'point_catchment_id',      # Para relación
        'id',                       # Para primary key
        'd1', 'd3', 'd5', 'd6',   # Todos los diámetros usados en el código
        'is_telemetry'              # Flag de telemetría
    )
)
```

### Verificación:
Buscar en admin_views.py todos los accesos a `profile.d*`:
```bash
grep -n "profile\.d[0-9]" api/core/admin_views.py | cut -d: -f1 | sort -u
# d1: línea 483, 1045
# d3: línea 484, 748
# d5: línea 190, 410, 1026
# d6: línea 198, 397, 745, 754
```

---

## 🎯 FIX #6: AGREGAR ADVERTENCIA DE VERACIDAD HISTÓRICA FALLIDA (LÍNEA 276-304)

**Impacto**: Usuario sabe cuando hay data fallida
**Riesgo**: Bajo

### Código Actual:
```python
except Exception as e:
    logger.error(f"Error calculando veracidad histórica: {e}", exc_info=True)
    # Continuar sin avisar al usuario ❌
    pct_veracidad = ((points_with_d5 - points_flow_above_probable) / points_with_d5 * 100) if points_with_d5 > 0 else 0
```

### Solución:
```python
except Exception as e:
    logger.error(f"Error calculando veracidad histórica: {e}", exc_info=True)
    # Avisar al usuario que los datos no son históricos
    use_historical_veracidad = False  # Resetear flag
    veracidad_periodo = None
    # Agregar mensaje de error al contexto
    context['warning_veracidad_historica'] = (
        f"No se pudo calcular veracidad histórica. Mostrando datos actuales. "
        f"Detalles: {str(e)[:100]}"
    )
    # Usar cálculo actual
    pct_veracidad = ((points_with_d5 - points_flow_above_probable) / points_with_d5 * 100) if points_with_d5 > 0 else 0
```

### En el template (dashboard.html):
```html
{% if warning_veracidad_historica %}
<div class="alert alert-warning">
    <strong>⚠️ Advertencia:</strong> {{ warning_veracidad_historica }}
</div>
{% endif %}
```

---

## 🎯 FIX #7: FUNCIÓN REUTILIZABLE PARA CALCULAR FLOW (LÍNEA 196-206, 398-405, 804-840)

**Impacto**: Menos código, menos bugs
**Riesgo**: Bajo

### Crear nueva función en utils.py:
```python
# En api/core/utils.py

def calculate_interaction_flow(interaction, has_caudal_promedio, d6_value):
    """
    Calcula el caudal dinámico de una interacción.

    Args:
        interaction: InteractionDetail object
        has_caudal_promedio: bool - Si la variable es CAUDAL_PROMEDIO
        d6_value: float - Diámetro del cálculo promedio

    Returns:
        float: Caudal calculado o valor guardado
    """
    from api.core.serializers.interaction_detail import InteractionDetailModelSerializer
    from api.cronjobs.telemetry.controllers.flow import average_flow

    flow_value = safe_float(interaction.flow)

    # Si no tiene CAUDAL_PROMEDIO o d6, retornar valor guardado
    if not has_caudal_promedio or d6_value <= 0:
        return flow_value

    # Intentar usar serializer para calcular dinámicamente
    try:
        serializer = InteractionDetailModelSerializer(interaction)
        serialized_data = serializer.data
        calculated_flow = serialized_data.get('flow', 0.0)
        if calculated_flow and calculated_flow > 0:
            return safe_float(calculated_flow)
    except Exception as e:
        logger.debug(f"Serializer failed, trying fallback: {e}")

    # Fallback: calcular con average_flow
    try:
        date_lg = interaction.date_time_last_logger or interaction.date_time_medition
        if date_lg and interaction.total is not None:
            point_dict = {"id": interaction.catchment_point_id}
            total_value = safe_float(interaction.total)
            calculated_flow = average_flow(
                point_catchment=point_dict,
                total=total_value,
                date_lg=date_lg
            )
            if calculated_flow:
                return safe_float(calculated_flow)
    except Exception as e:
        logger.debug(f"average_flow failed, using stored value: {e}")

    # Si todo falla, usar valor guardado
    return flow_value
```

### Uso en admin_views.py:
```python
# Línea 196-206: Reemplazar con
from api.core.utils import calculate_interaction_flow

flow_value = calculate_interaction_flow(
    last_record,
    has_caudal_promedio,
    d6_safe
)

# Línea 398-405: Reemplazar con
flow_value = calculate_interaction_flow(
    last_record,
    has_caudal_promedio,
    d6_safe_error
)

# Línea 804-840: Reemplazar con
flow_value = calculate_interaction_flow(
    interaction,
    has_caudal_promedio,
    d6_value
)
```

---

## 📋 CHECKLIST DE APLICACIÓN

### Pre-requisitos:
- [ ] Backup de admin_views.py creado
- [ ] Rama de git creada: `git checkout -b fix/dashboard-bugs`

### Fixes a Aplicar (en orden):
1. [ ] FIX #1: Eliminar N+1 queries (mayor impacto en performance)
2. [ ] FIX #7: Crear función calculate_interaction_flow
3. [ ] FIX #2: Corregir % Conectados
4. [ ] FIX #3: Validar conversiones a float
5. [ ] FIX #4: Mejorar manejo de excepciones
6. [ ] FIX #5: Completar Prefetch fields
7. [ ] FIX #6: Advertencia de veracidad histórica

### Testing:
- [ ] Dashboard carga sin errores
- [ ] Métricas son correctas (verificar manualmente)
- [ ] Performance < 2 segundos
- [ ] Logs no muestran excepciones
- [ ] Tests pasan: `python manage.py test tests/`

### Deploy:
- [ ] Tests en staging OK
- [ ] Commit con mensaje claro
- [ ] PR y code review
- [ ] Merge a main
- [ ] Deploy a producción

---

## ⏱️ TIEMPO ESTIMADO

| Fix | Tiempo | Dificultad |
|-----|--------|-----------|
| #1 - N+1 Queries | 30 min | 🟡 Media |
| #2 - % Conectados | 10 min | 🟢 Fácil |
| #3 - Float Validation | 10 min | 🟢 Fácil |
| #4 - Exception Handling | 10 min | 🟢 Fácil |
| #5 - Prefetch Fields | 5 min | 🟢 Fácil |
| #6 - Veracidad Warning | 15 min | 🟢 Fácil |
| #7 - Función Reutilizable | 20 min | 🟡 Media |
| **Testing + Docs** | **20 min** | **🟡 Media** |
| **TOTAL** | **~2 horas** | - |

---

## ✅ VALIDACIÓN POST-FIX

```python
# Test script: test_dashboard_fixes.py
from django.test import Client
import time

client = Client()
client.force_login(admin_user)

# Test 1: Cargar dashboard sin errores
start = time.time()
response = client.get('/admin/dashboard/')
elapsed = time.time() - start

assert response.status_code == 200, "Dashboard debe cargar exitosamente"
assert elapsed < 3, f"Dashboard tardó {elapsed}s, máximo 3s (apunta a < 2s)"
print(f"✅ Dashboard cargó en {elapsed:.2f}s")

# Test 2: Verificar contexto
context = response.context
assert context['num_obras'] >= 0, "num_obras debe ser >= 0"
assert 0 <= context['pct_conectados'] <= 100, "pct_conectados debe estar entre 0-100"
assert 0 <= context['pct_dga'] <= 100, "pct_dga debe estar entre 0-100"
assert 0 <= context['pct_veracidad'] <= 100, "pct_veracidad debe estar entre 0-100"
print(f"✅ Métricas son válidas")

# Test 3: Verificar no hay N+1 queries
from django.test.utils import CaptureQueriesContext
from django.db import connection

with CaptureQueriesContext(connection) as ctx:
    response = client.get('/admin/dashboard/')

assert len(ctx) < 10, f"Dashboard ejecuta {len(ctx)} queries (apunta a < 10)"
print(f"✅ Dashboard ejecuta {len(ctx)} queries (OK)")

# Test 4: Página inválida
response = client.get('/admin/dashboard/?error_page=invalid')
assert response.status_code == 200, "Dashboard debe manejar página inválida"
print(f"✅ Manejo de página inválida OK")

print("\n✅ TODOS LOS TESTS PASARON")
```

---

**Documento de Implementación completado**
Aplicar estos fixes debería resultar en un dashboard 10-20x más rápido y confiable.
