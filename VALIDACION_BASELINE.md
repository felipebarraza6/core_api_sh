# Validación Baseline - Estado Actual del Sistema

**Fecha de creación**: 2025-01-XX  
**Objetivo**: Documentar el estado actual del sistema ANTES de realizar cualquier modificación

## Endpoints API Documentados

### 1. `/api/interaction_detail/` (InteractionXLS)
- **Tipo**: ViewSet con soporte XLSX y JSON
- **Serializer**: `InteractionDetailModelSerializer`
- **Campos esperados en respuesta**:
  - `id`, `catchment_point`, `date_time_medition`, `date_time_last_logger`
  - `flow`, `total`, `total_diff`, `total_today_diff`
  - `pulses`, `nivel`, `water_table`
  - `send_dga`, `return_dga`, `n_voucher`, `is_error`
  - `days_not_conection`, `notification`
  - `is_average` (calculado), `flow_type` (calculado)
- **Comportamiento especial**: Calcula `flow` dinámicamente si tiene `CAUDAL_PROMEDIO`
- **Filtros**: `catchment_point`, `send_dga`, `date_time_medition`

### 2. `/api/interaction_detail_json/` (InteractionDetailViewSet)
- **Tipo**: ViewSet estándar con paginación
- **Serializer**: `InteractionDetailModelSerializer`
- **Optimizaciones**: Usa `select_related` y `prefetch_related`
- **Mismos campos que** `/api/interaction_detail/`

### 3. `/api/interaction_detail_override/` (InteractionDetailOverrideViewSet)
- **Tipo**: ViewSet sin paginación
- **Serializer**: `InteractionDetailModelSerializer`
- **Comportamiento**: Sin paginación (retorna todos los registros)
- **Mismos campos que** `/api/interaction_detail/`

### 4. `/api/interaction_detail_override_month/` (InteractionDetailOverrideMonthViewSet)
- **Tipo**: ViewSet sin paginación con filtro por `created`
- **Serializer**: `InteractionDetailModelSerializer`
- **Filtros adicionales**: `created` (además de los estándar)

### 5. `/api/interaction_detail_override_month_xlsx/` (InteractionXLSMonth)
- **Tipo**: Exportación Excel mensual
- **Serializer**: `InteractionDetailModelSerializer`

### 6. `/api/interaction_detail_dga/` (InteractionXLSDga)
- **Tipo**: Exportación Excel para DGA
- **Serializer**: `InteractionDetailModelSerializerNoProcessing`

### 7. `/admin/dashboard/` (admin_dashboard_view)
- **Tipo**: Vista Django Admin
- **Métricas calculadas**:
  - `num_obras`: Puntos con código de obra
  - `pct_conectados`: % de puntos con telemetría activa
  - `pct_dga`: % de puntos con cumplimiento DGA activo
  - `pct_veracidad`: % de puntos que no superan caudal probable
  - `stats_caudal_probable.con_desconexion`: Puntos desconectados
  - `registro_errores`: Registros con errores
  - `pct_cola_dga`: % de registros en cola DGA
  - `notificaciones_pendientes`: Errores sin incidencias

## Cronjobs Documentados

### Telemetría

#### 1. `twin.py` (1/hora)
- **Frecuencia**: Cada hora
- **Filtro**: `is_tdata=True, is_telemetry=True, frecuency="60"`
- **Procesa**: Variables TOTALIZADO, NIVEL, CAUDAL, CAUDAL_PROMEDIO
- **Lógica**: Usa `get_data_tdata()` para obtener datos

#### 2. `twin_f1.py` (1/minuto)
- **Frecuencia**: Cada minuto
- **Filtro**: `is_tdata=True, is_telemetry=True, frecuency="1"`
- **Misma lógica que** `twin.py`

#### 3. `twin_f5.py` (5/minutos)
- **Frecuencia**: Cada 5 minutos
- **Filtro**: `is_tdata=True, is_telemetry=True, frecuency="5"`
- **Misma lógica que** `twin.py`

#### 4. `nettra.py` (1/hora)
- **Frecuencia**: Cada hora
- **Filtro**: `is_thethings=True, is_telemetry=True, frecuency="60"`
- **Procesa**: Variables usando `get_data_thethings()`

#### 5. `nettra_f5.py` (5/minutos)
- **Frecuencia**: Cada 5 minutos
- **Filtro**: `is_thethings=True, is_telemetry=True, frecuency="5"`
- **Misma lógica que** `nettra.py`

#### 6. `novus.py` (1/hora)
- **Frecuencia**: Cada hora
- **Filtro**: `is_novus=True, is_telemetry=True, frecuency="60"`
- **Procesa**: Variables usando `get_data_tago()`

### DGA

#### 1. `cron_dga.py`
- **Función**: Envía registros pendientes a DGA
- **Límite**: Máximo 10 registros por ejecución
- **Filtro**: `send_dga=True`, excluye `catchment_point=1`
- **Orden**: Por `created` (más antiguos primero)
- **Cálculo de caudal**: 
  - Si tiene `CAUDAL_PROMEDIO`: Calcula dinámicamente con `_calculate_dynamic_flow()`
  - Si no: Usa `register.flow`
  - Si `total_diff=0`: Fuerza `flow=0.0`

## Cálculos Críticos Documentados

### Cálculo de Caudal Promedio
- **Función**: `average_flow()` en `api/cronjobs/telemetry/controllers/flow.py`
- **Fórmula**: `((total_actual - total_anterior) / Δt_seg) * 1000`
- **Comportamiento**:
  - Busca registro anterior por `date_time_last_logger` o `date_time_medition`
  - Calcula diferencia de tiempo en segundos
  - Calcula diferencia de total en m³
  - Si `diff <= 0`: Retorna 0.0
  - Si `diff > 0`: Calcula caudal en L/s

### Cálculo de Caudal para DGA
- **Función**: `_calculate_dynamic_flow()` en `api/cronjobs/dga/cron_dga.py`
- **Comportamiento**:
  - Busca registro anterior
  - Usa `average_flow()` para calcular
  - Retorna 0.0 si falla

### Validación de Frecuencia DGA
- **Función**: `validate_frequency()` en `api/cronjobs/telemetry/controllers/unified_processing.py`
- **Estándares**:
  - `MAYOR`: Cada hora (minuto == 0)
  - `MEDIO`: Diario (hora == 0 y minuto == 0)
  - `MENOR`: Mensual (día == 1, hora == 0, minuto == 0)
  - `CAUDALES_MUY_PEQUENOS`: Semestral (meses 1 o 7, día == 1)

## Notas Importantes

1. **Caudal Promedio NO se guarda**: Se calcula dinámicamente en serializers y cron_dga
2. **Total se modifica**: Se suma `d6` al `total` en el serializer
3. **Validaciones**: Si `total_diff=0`, el caudal se fuerza a 0.0
4. **Optimizaciones**: Se usan `select_related` y `prefetch_related` en varios lugares

