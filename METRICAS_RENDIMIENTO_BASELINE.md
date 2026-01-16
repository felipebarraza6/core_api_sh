# Métricas de Rendimiento Baseline

**Fecha de creación**: 2025-01-XX  
**Objetivo**: Documentar métricas de rendimiento actuales antes de optimizaciones

## Endpoints - Tiempos de Respuesta

### Métricas a Medir (Pendiente de ejecución)

1. `/api/interaction_detail/`
   - Tiempo promedio: _pendiente_
   - Tiempo p95: _pendiente_
   - Tiempo p99: _pendiente_
   - Queries ejecutadas: _pendiente_

2. `/api/interaction_detail_json/`
   - Tiempo promedio: _pendiente_
   - Queries ejecutadas: _pendiente_

3. `/admin/dashboard/`
   - Tiempo promedio: _pendiente_
   - Queries ejecutadas: _pendiente_

## Cronjobs - Tiempos de Ejecución

### Métricas a Medir (Pendiente de ejecución)

1. `twin.py` (1/hora)
   - Tiempo promedio: _pendiente_
   - Registros procesados: _pendiente_

2. `twin_f1.py` (1/minuto)
   - Tiempo promedio: _pendiente_
   - Registros procesados: _pendiente_

3. `cron_dga.py`
   - Tiempo promedio: _pendiente_
   - Registros procesados: _pendiente_
   - Tasa de éxito: _pendiente_

## Queries Lentas Identificadas

### Pendiente de análisis con django-debug-toolbar

- _Por identificar_

## Notas

- Estas métricas se medirán en producción/staging antes de hacer cambios
- Se usarán como referencia para validar mejoras de rendimiento
- Cualquier optimización debe mantener o mejorar estos tiempos

