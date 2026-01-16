---
name: Filtrar registros por estándar DGA
overview: "Modificar la consulta de registros recientes para mostrar el último registro que se debía enviar a DGA según el estándar de cada punto (MAYOR: último minuto 0, MEDIO: último 00:00, MENOR: último día 1 00:00, CAUDALES_MUY_PEQUENOS: último semestral)"
todos:
  - id: modify_query_logic
    content: Modificar la lógica de consulta para filtrar registros según estándar DGA de cada punto
    status: pending
  - id: implement_standard_filters
    content: Implementar filtros específicos para cada estándar (MAYOR, MEDIO, MENOR, CAUDALES_MUY_PEQUENOS)
    status: pending
  - id: add_fallback_logic
    content: Agregar lógica de fallback si no hay registro según estándar
    status: pending
  - id: test_standard_filtering
    content: Verificar que los registros mostrados correspondan al estándar y permitan verificar cumplimiento DGA
    status: pending
---

# Plan: Filtrar Registros Recientes por Estándar DGA

## Objetivo

Modificar la tabla de "Registros Recientes" para que muestre el último registro que se debía enviar a DGA según el estándar de cada punto, permitiendo verificar el cumplimiento (si tiene voucher DGA o no).

## Lógica por Estándar

1. **MAYOR**: Último registro con `minute == 0` de la hora más reciente (ej: si son las 14:30, mostrar registro de las 14:00)
2. **MEDIO**: Último registro con `hour == 0 and minute == 0` (00:00 del día más reciente)
3. **MENOR**: Último registro con `day == 1 and hour == 0 and minute == 0` (1er día del mes más reciente a las 00:00)
4. **CAUDALES_MUY_PEQUENOS**: Último registro con `month in [1, 7] and day == 1 and hour == 0 and minute == 0` (enero o julio día 1 a las 00:00)
5. **SIN_ESTANDAR**: Último registro disponible (sin filtro de frecuencia)

## Archivos a Modificar

### 1. `api/core/admin_views.py`

**Cambio en la lógica de obtención de registros (líneas 533-605)**

**Antes**: Se obtiene el último registro de las últimas 24 horas o el más reciente disponible.

**Después**: Para cada punto, obtener el último registro que corresponde a su estándar DGA.

**Implementación**:

1. Para cada punto con código de obra, obtener su estándar desde `dga_profile.standard`
2. Según el estándar, filtrar los registros:

   - **MAYOR**: Filtrar registros con `date_time_medition.minute == 0`, ordenar descendente, tomar el primero
   - **MEDIO**: Filtrar registros con `date_time_medition.hour == 0 and date_time_medition.minute == 0`, ordenar descendente, tomar el primero
   - **MENOR**: Filtrar registros con `date_time_medition.day == 1 and date_time_medition.hour == 0 and date_time_medition.minute == 0`, ordenar descendente, tomar el primero
   - **CAUDALES_MUY_PEQUENOS**: Filtrar registros con `date_time_medition.month in [1, 7] and date_time_medition.day == 1 and date_time_medition.hour == 0 and date_time_medition.minute == 0`, ordenar descendente, tomar el primero
   - **SIN_ESTANDAR**: Último registro disponible (sin filtro)

3. Si no se encuentra registro que cumpla el estándar, mostrar el último registro disponible como fallback

**Código específico a modificar**:

```python
# Líneas 533-605: Reemplazar la lógica de obtención de registros
# En lugar de obtener el último registro simple, obtener según estándar

recent_interactions = []
for point_id in visible_points_with_code:
    # Obtener estándar del punto
    dga_profile = DgaDataConfigCatchment.objects.filter(
        point_catchment_id=point_id
    ).first()
    
    if not dga_profile or not dga_profile.standard:
        standard = "SIN_ESTANDAR"
    else:
        standard = dga_profile.standard
    
    # Filtrar según estándar
    base_query = InteractionDetail.objects.filter(
        catchment_point_id=point_id
    )
    
    if standard == "MAYOR":
        # Último registro con minuto == 0
        last_record = base_query.filter(
            date_time_medition__minute=0
        ).order_by('-date_time_medition', '-id').first()
    elif standard == "MEDIO":
        # Último registro con hour == 0 and minute == 0
        last_record = base_query.filter(
            date_time_medition__hour=0,
            date_time_medition__minute=0
        ).order_by('-date_time_medition', '-id').first()
    elif standard == "MENOR":
        # Último registro con day == 1, hour == 0, minute == 0
        last_record = base_query.filter(
            date_time_medition__day=1,
            date_time_medition__hour=0,
            date_time_medition__minute=0
        ).order_by('-date_time_medition', '-id').first()
    elif standard == "CAUDALES_MUY_PEQUENOS":
        # Último registro semestral (enero o julio día 1 a las 00:00)
        last_record = base_query.filter(
            date_time_medition__month__in=[1, 7],
            date_time_medition__day=1,
            date_time_medition__hour=0,
            date_time_medition__minute=0
        ).order_by('-date_time_medition', '-id').first()
    else:
        # SIN_ESTANDAR: último registro disponible
        last_record = base_query.order_by('-date_time_medition', '-id').first()
    
    # Si no se encuentra registro según estándar, usar el último disponible como fallback
    if not last_record:
        last_record = base_query.order_by('-date_time_medition', '-id').first()
    
    if last_record:
        recent_interactions.append(last_record)
```

**Nota**: Django ORM no soporta directamente `__minute`, `__hour`, `__day`, `__month` en filtros. Necesitamos usar `Extract` de `django.db.models.functions` o filtrar después de obtener los registros.

**Alternativa más eficiente**: Usar `Extract` para filtrar en la base de datos:

```python
from django.db.models.functions import Extract

if standard == "MAYOR":
    last_record = base_query.annotate(
        minute=Extract('date_time_medition', 'minute')
    ).filter(minute=0).order_by('-date_time_medition', '-id').first()
```

## Validaciones

1. Verificar que los registros mostrados correspondan al estándar de cada punto
2. Si un punto tiene estándar MEDIO y no tiene voucher DGA, significa que no completó el envío
3. Mantener el orden: primero desconectados, luego por fecha descendente
4. Asegurar que siempre se muestre un registro por punto (usar fallback si no hay registro según estándar)

## Consideraciones

- Si un punto no tiene registros que cumplan su estándar, mostrar el último registro disponible como fallback
- El template ya muestra el voucher DGA, así que se podrá verificar fácilmente el cumplimiento
- Los registros se seguirán ordenando: primero desconectados, luego por fecha descendente