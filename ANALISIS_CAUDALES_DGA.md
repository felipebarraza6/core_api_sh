# Análisis de Cálculo de Caudales para DGA

**Fecha de creación**: 2025-01-XX  
**Objetivo**: Analizar el problema del cálculo de caudales para estándar MEDIO

## Problema Identificado

### Situación Actual

Para el estándar **MEDIO**, el sistema actualmente:

1. **Procesa diariamente** (a las 00:00) según `validate_frequency()`
2. **Calcula caudal** usando `_calculate_dynamic_flow()` que:
   - Busca el registro anterior al actual
   - Calcula: `((total_actual - total_anterior) / Δt_seg) * 1000`
   - Esto da un **caudal entre dos registros puntuales**, no un promedio diario

### Requisito DGA para Estándar MEDIO

Según los requisitos de DGA, para estándar **MEDIO** se debe enviar:
- **Caudal medio diario**: Promedio de todas las horas del día anterior (00:00 a 23:59)

### Diferencia Crítica

- **Actual**: Caudal entre registro actual y el anterior (puede ser de hace horas)
- **Requerido**: Promedio de todos los caudales horarios del día anterior

## Análisis Técnico

### Código Actual

**Ubicación**: `api/cronjobs/dga/cron_dga.py`

```python
def _calculate_dynamic_flow(register: InteractionDetail) -> float:
    # Busca registro anterior
    previous_register = InteractionDetail.objects.filter(
        catchment_point=register.catchment_point,
        date_time_medition__lt=register.date_time_medition
    ).order_by('-date_time_medition').first()
    
    # Calcula entre dos registros
    calculated_flow = average_flow(...)
```

**Problema**: Solo usa 2 registros, no calcula promedio diario.

### Cálculo Requerido para MEDIO

```python
def calculate_daily_average_flow(register: InteractionDetail, dga_config: DgaDataConfigCatchment) -> float:
    # 1. Obtener día anterior (00:00 a 23:59)
    # 2. Obtener todos los registros del día anterior
    # 3. Agrupar por hora (o usar todos los registros)
    # 4. Calcular caudal de cada registro
    # 5. Promediar todos los caudales
    # 6. Retornar promedio diario
```

## Impacto

### Puntos Afectados

- Todos los puntos con `standard="MEDIO"` y `send_dga=True`
- Los datos enviados a DGA pueden ser incorrectos
- Puede causar rechazos o inconsistencias en la API DGA

### Validación Necesaria

1. Identificar cuántos puntos tienen estándar MEDIO
2. Analizar registros históricos enviados
3. Comparar cálculo actual vs requerido
4. Validar con datos reales

## Próximos Pasos

1. **Ejecutar análisis** usando `caudal_analysis.py`
2. **Validar requisitos** con documentación DGA
3. **Implementar cálculo correcto** en archivo separado
4. **Validar exhaustivamente** antes de integrar
5. **Integrar gradualmente** con flag de feature

## Notas

- Este análisis NO modifica ningún dato
- Se debe validar exhaustivamente antes de cambiar producción
- Otros estándares (MAYOR, MENOR) pueden tener requisitos similares

