# Análisis de Operaciones y Funciones de Telemetría

**Fecha:** 2026-01-20  
**Sistema:** SmartHydro Core API

---

## 📋 Índice

1. [Arquitectura General](#arquitectura-general)
2. [Motor de Fórmulas (FormulaEngine)](#motor-de-fórmulas)
3. [Procesadores Legacy](#procesadores-legacy)
4. [Controladores Unificados](#controladores-unificados)
5. [Servicio de Configuración](#servicio-de-configuración)
6. [Proveedores de Datos](#proveedores-de-datos)
7. [Flujo de Datos Completo](#flujo-de-datos)
8. [Validaciones y Protecciones](#validaciones-y-protecciones)
9. [Resumen de Funciones](#resumen-de-funciones)

---

## 🏗️ Arquitectura General {#arquitectura-general}

El sistema de telemetría tiene una arquitectura en capas:

```
┌─────────────────────────────────────────────────────────────┐
│                     CAPA DE INGESTA                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   TData     │  │   Tago      │  │  ThingsIO   │  ...    │
│  │   (Legacy)  │  │   (Legacy)  │  │  (Legacy)   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
└─────────┼────────────────┼────────────────┼─────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                 CAPA DE PROCESAMIENTO                        │
│  ┌────────────────────────────────────────────────────┐     │
│  │           unified_processing.py                     │     │
│  │  ┌──────────────────────────────────────────────┐  │     │
│  │  │  process_variable_safely()                    │  │     │
│  │  │    ├─→ FormulaEngine (NUEVO)                 │  │     │
│  │  │    └─→ Procesadores Legacy (fallback)        │  │     │
│  │  └──────────────────────────────────────────────┘  │     │
│  └────────────────────────────────────────────────────┘     │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  flow.py    │  │  total.py   │  │  nivel.py   │         │
│  │  (Legacy)   │  │  (Legacy)   │  │  (Legacy)   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                 CAPA DE ALMACENAMIENTO                       │
│  ┌────────────────────────────────────────────────────┐     │
│  │           TelemetryRecord                          │     │
│  │  {data: {total, flow, nivel, ...}, metadata: {...}}│     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Motor de Fórmulas (FormulaEngine) {#motor-de-fórmulas}

**Ubicación:** `api/telemetry/processing/formula_engine.py`

### Descripción
Motor unificado que reemplaza los procesadores específicos (flow.py, total.py, nivel.py) con un sistema basado en fórmulas configurables desde la base de datos.

### Clase: `FormulaEngine`

```python
class FormulaEngine:
    """
    Motor de evaluación de fórmulas dinámicas.
    
    Soporta referencias a:
    - {var_code}: Otras variables del punto
    - {config.code}: Configuración del punto
    - {system.key}: SystemConfiguration
    - {prev.var_code}: Valores anteriores
    - {time.*}: Contexto temporal
    """
```

### Métodos Principales

#### 1. `__init__(self, point_id: int)`
Inicializa el motor para un punto específico.

**Parámetros:**
- `point_id`: ID del CatchmentPoint

**Acciones:**
- Carga el punto con su esquema de configuración
- Carga las configuraciones del punto (`get_config_dict()`)
- Prepara contextos para fórmulas

#### 2. `evaluate(formula, current_values, current_timestamp=None) -> float`
Evalúa una fórmula con el contexto actual.

**Parámetros:**
- `formula`: Fórmula con tokens (ej: `{pulses} * {config.factor} / 1000`)
- `current_values`: Diccionario con valores actuales
- `current_timestamp`: Timestamp del registro (opcional)

**Proceso:**
1. Carga valores previos si hay timestamp
2. Calcula contexto temporal (diff_seconds, hour, day, etc.)
3. Reemplaza tokens por valores
4. Valida que solo contenga operadores seguros
5. Evalúa de forma segura con `eval()`

**Retorna:** Resultado numérico o 0.0 en caso de error

#### 3. `process_variable(variable, raw_value, current_values, current_timestamp=None) -> float`
Procesa una variable usando su fórmula configurada.

**Parámetros:**
- `variable`: Instancia de CoreVariable
- `raw_value`: Valor crudo del proveedor
- `current_values`: Valores actuales de todas las variables
- `current_timestamp`: Timestamp del registro

**Proceso:**
1. Agrega valor crudo a current_values
2. Obtiene fórmula (de CoreVariable o VariableType)
3. Si no hay fórmula, aplica scale_factor y offset
4. Si hay fórmula, la evalúa con `evaluate()`

#### 4. `get_formula_for_variable(variable, current_values, current_timestamp=None) -> str`
Obtiene la fórmula a usar para una variable.

**Prioridad:**
1. `CoreVariable.formula` (si existe)
2. `VariableType.default_formula` (si existe)
3. None (sin fórmula)

### Métodos Internos

#### `_load_context()`
Carga todas las fuentes de datos para fórmulas:
- Punto de captación
- Configuraciones del punto
- Variables activas

#### `_load_previous_values(current_timestamp) -> Dict`
Carga valores del último registro de telemetría.

#### `_load_time_context(current_timestamp, previous_timestamp=None) -> Dict`
Calcula contexto temporal:
- `diff_seconds`, `diff_minutes`, `diff_hours`
- `hour`, `minute`, `day`, `month`, `year`

#### `_replace_tokens(formula, current_values) -> str`
Reemplaza tokens por valores:

| Token | Significado | Ejemplo |
|-------|-------------|---------|
| `{var_code}` | Valor de variable actual | `{pulses}` → `15000` |
| `{config.code}` | Configuración del punto | `{config.d3}` → `45.5` |
| `{system.key}` | SystemConfiguration | `{system.max_flow}` → `150` |
| `{prev.var_code}` | Valor anterior | `{prev.total}` → `1234` |
| `{time.*}` | Contexto temporal | `{time.diff_seconds}` → `3600` |

### Namespace Seguro

```python
namespace = {
    '__builtins__': {},
    'abs': abs,
    'min': min,
    'max': max,
    'round': round,
    'pow': pow,
}
```

### Ejemplos de Fórmulas

```python
# Totalizado con factor de pulsos
formula = "({pulses} * {config.pulses_factor}) / 1000 + {config.addition}"

# Nivel freático
formula = "{config.d3} - {nivel}"

# Caudal promedio
formula = "(({total} - {prev.total}) / {time.diff_seconds}) * 1000"

# Condicional con hora
formula = "{flow} if {time.hour} < 22 else 0"
```

---

## 📦 Procesadores Legacy {#procesadores-legacy}

### flow.py - Procesamiento de Caudales

**Ubicación:** `api/telemetry/ingestion/controllers/flow.py`

#### `instantaneous_flow(value, convert_to_lt, scale_divisor=None)`
Calcula caudal instantáneo.

**Parámetros:**
- `value`: Valor del sensor
- `convert_to_lt`: Convertir a L/s (divide por 3.6)
- `scale_divisor`: Divisor de escala opcional

**Proceso:**
1. Convierte valor a float
2. Aplica divisor de escala si existe
3. Convierte a L/s si se requiere
4. Valida que no exceda precisión máxima

**Retorna:** Caudal en L/s (2 decimales)

#### `average_flow(point_catchment, total, date_lg, exclude_id=None, current_logger_dt=None)`
Calcula caudal promedio basado en diferencia de totales.

**Fórmula:**
```
Caudal (L/s) = ((total_actual - total_anterior) / Δt_seg) * 1000
```

**Validaciones Anti-Disparo:**
1. Gap de tiempo máximo (configurable, default 2h)
2. Días sin conexión en registro anterior
3. Consumo por hora máximo (configurable, default 500 m³/h)
4. Caudal máximo razonable (configurable, default 150 L/s)

---

### total.py - Procesamiento de Totalizados

**Ubicación:** `api/telemetry/ingestion/controllers/total.py`

#### `total_m3(pulses_factor, value, point_catchment, variable_id=None, return_full_details=False)`
Calcula total en m³ con lógica de reset.

**Fórmula:**
```
Total (m³) = ((pulsos × factor) / 1000) + offset
```

**Lógica de Reset:**
1. Detecta pulsos negativos → Error de ingesta
2. Detecta salto masivo → Bloquea
3. Detecta glitch (valor 0) → Ignora
4. Detecta reset real (0 < actual < anterior) → Actualiza addition

**Proceso de Reset:**
```python
if 0 < current_pulses < last_pulses:
    # Reset real detectado
    amount_to_add = (last_pulses * factor) / 1000.0
    profile.addition += amount_to_add
    # Crear notificación
```

#### `total_hour(total, point_catchment, current_dt=None)`
Diferencia contra la medición anterior.

**Validaciones:**
- Diff negativa → Clamp a 0
- Diff excesiva (> 500) → Clamp a 0

#### `total_day(point_catchment, current_dt=None, current_total=None)`
Acumulado del día.

**Fórmula:**
```
Acumulado = Total_actual - Primer_total_del_día
```

**Validaciones:**
- Diff negativa → Clamp a 0
- Diff día excesiva (> 10000) → Clamp a 0

---

### nivel.py - Procesamiento de Niveles

**Ubicación:** `api/telemetry/ingestion/controllers/nivel.py`

#### `nivel_mt(value, base, point_catchment_id=None, position=None)`
Calcula nivel en metros.

**Fórmula:**
```
Nivel (m) = value / base
```

**Validaciones:**
- Nivel negativo o cero → Retorna "00.00"
- Excede precisión → Retorna "00.00"

#### `water_table(value, position)`
Calcula nivel freático.

**Fórmula:**
```
Nivel Freático = position (d3) - nivel
```

---

## 🎯 Controladores Unificados {#controladores-unificados}

**Ubicación:** `api/telemetry/ingestion/controllers/unified_processing.py`

### Función Principal: `process_variable_safely()`

```python
def process_variable_safely(
    variable: Dict,
    data: Dict,
    point_catchment: Dict,
    created_register: Dict,
    date_time_last_logger_total: Optional[str] = None
) -> tuple:
```

**Flujo:**
1. Valida min/max del valor
2. Intenta usar FormulaEngine si está disponible
3. Si falla, usa procesadores legacy según `type_variable`

### Funciones de Procesamiento Específico

#### `process_totalizado_variable(data, variable, point_catchment, created_register)`
Procesa variable tipo TOTALIZADO.

**Acciones:**
1. Convierte valor a entero
2. Asigna pulsos al registro
3. Calcula total_m3
4. Calcula total_diff (diferencia hora)
5. Calcula total_today_diff (acumulado día)
6. Asigna timestamp del logger
7. Calcula días sin conexión

#### `process_nivel_variable(data, variable, point_catchment, created_register)`
Procesa variable tipo NIVEL.

**Acciones:**
1. Maneja nivel negativo (busca último válido)
2. Aplica offset si existe
3. Obtiene d3 de configuración
4. Calcula nivel_mt
5. Calcula water_table

#### `process_caudal_variable(data, variable, point_catchment, created_register)`
Procesa variable tipo CAUDAL instantáneo.

#### `process_caudal_promedio_variable(date_time_last_logger_total, created_register, point_catchment)`
Procesa variable tipo CAUDAL_PROMEDIO.

**Nota:** No guarda flow en registro, se calcula dinámicamente en serializers.

### Funciones Auxiliares

#### `save_telemetry_data(point_id, created_register, processed_variables=None)`
Guarda datos en TelemetryRecord.

**Estructura del registro:**
```python
TelemetryRecord.objects.create(
    point_id=point_id,
    timestamp=dt_medition,
    data=v3_data,          # {total, flow, nivel, pulses, ...}
    metadata=metadata,      # {last_logger_timestamp, device_id, ...}
    send_dga=False,
    is_error=False,
    is_partial=False
)
```

#### `get_data_with_retry(getter_func, *args, max_retries=None, backoff_factor=None)`
Retry inteligente con backoff exponencial.

**Configuración dinámica:**
- `retry.max_retries` (default: 3)
- `retry.backoff_factor` (default: 2)

#### `validate_frequency(point_catchment, current_time) -> bool`
Valida si debe procesar según estándar DGA.

| Estándar | Frecuencia |
|----------|------------|
| MAYOR | Cada hora (minuto == 0) |
| MEDIO | Diario (00:00) |
| MENOR | Mensual (día 1, 00:00) |
| CAUDALES_MUY_PEQUENOS | Semestral (Enero/Julio) |
| SIN_ESTANDAR | Siempre procesa |

#### `calculate_days_not_connection(created_register, chile_tz, point_catchment=None)`
Calcula días sin conexión.

**Casos:**
1. Con timestamp del logger → Usa diferencia directa
2. Sin timestamp → Busca último registro válido en BD

#### `determine_dga_send(point_catchment, chile_tz) -> bool`
Determina si debe enviar datos a DGA.

---

## ⚙️ Servicio de Configuración {#servicio-de-configuración}

**Ubicación:** `api/core/services/config_service.py`

### Clase: `ConfigService`

Servicio centralizado para obtener configuraciones del sistema con:
- Cache (5 minutos por defecto)
- Fallback a valores por defecto
- Tipado automático

### Configuraciones Por Defecto

```python
DEFAULT_CONFIGS = {
    # TELEMETRY - Protecciones Anti-Disparo
    'telemetry.max_flow_ls': 150.0,           # Máx caudal L/s
    'telemetry.max_time_gap_hours': 2,         # Máx gap tiempo (horas)
    'telemetry.max_diff_m3_per_hour': 500,     # Máx consumo/hora
    'telemetry.max_diff_m3_per_day': 10000,    # Máx consumo/día
    'telemetry.pulses_factor_default': 1000,   # Factor pulsos default
    'telemetry.max_value_precision': 1000,     # Precisión máxima
    
    # MAINTENANCE - Retención
    'maintenance.telemetry_retention_days': 90,
    'maintenance.notifications_retention_days': 180,
    
    # RETRY - Reintentos
    'retry.max_retries': 3,
    'retry.backoff_factor': 2,
    
    # CACHE
    'cache.telemetry_ttl': 900,
    'cache.config_ttl': 300,
}
```

### Métodos

```python
# Obtener valor genérico
ConfigService.get('telemetry.max_flow_ls', default=150.0)

# Obtener como entero
ConfigService.get_int('retry.max_retries', default=3)

# Obtener como float
ConfigService.get_float('telemetry.max_flow_ls', default=150.0)

# Obtener como booleano
ConfigService.get_bool('feature.enabled', default=False)

# Establecer configuración
ConfigService.set('telemetry.max_flow_ls', 200.0, category='TELEMETRY')

# Inicializar defaults
ConfigService.initialize_defaults()

# Limpiar cache
ConfigService.clear_cache()
```

---

## 📡 Proveedores de Datos {#proveedores-de-datos}

### Getters Legacy (DEPRECATED)

**Ubicación:** `api/telemetry/ingestion/getters/`

| Archivo | Proveedor | Estado |
|---------|-----------|--------|
| `tdata.py` | TwinDimension | DEPRECATED |
| `tago.py` | Tago.io | DEPRECATED |
| `thingsio.py` | TheThingsIO | DEPRECATED |

### Estructura del Getter

```python
def get_data_tdata(token_service, str_variable):
    """
    Obtener datos de TDATA.
    
    Returns:
        {
            "date_time": "2026-01-20T15:30:00",
            "value": 12345
        }
    """
```

### Sistema Nuevo (Dinámico)

Se recomienda usar el sistema de proveedores dinámicos:
```python
from api.telemetry.providers.manager import get_data_with_provider
```

---

## 🔄 Flujo de Datos Completo {#flujo-de-datos}

### 1. Ingesta (Cronjob)

```python
# Ejemplo: twin.py cronjob
for point in active_points:
    for variable in point.variables:
        # 1. Obtener datos del proveedor
        data = get_data_with_retry(get_data_tdata, token, variable.provider_key)
        
        # 2. Procesar variable
        _, created_register = process_variable_safely(
            variable, data, point, created_register
        )
    
    # 3. Guardar registro
    save_telemetry_data(point['id'], created_register)
```

### 2. Procesamiento con FormulaEngine

```python
# Interno de process_variable_safely
engine = FormulaEngine(point_id)

# Obtener fórmula (de CoreVariable o VariableType)
formula = engine.get_formula_for_variable(core_var, current_values)

# Evaluar
processed_value = engine.evaluate(formula, current_values, timestamp)
```

### 3. Almacenamiento

```python
TelemetryRecord.objects.create(
    point_id=point_id,
    timestamp=dt_medition,
    data={
        'total': 12345,
        'flow': 2.45,
        'nivel': 23.5,
        'water_table': 22.0,
        'pulses': 12345000,
        'total_diff': 5,
        'total_today_diff': 120
    },
    metadata={
        'last_logger_timestamp': '2026-01-20T15:30:00',
        'days_not_connection': 0,
        'device_id': 'ABC123',
        'processed_at': '2026-01-20T15:31:00'
    }
)
```

---

## 🛡️ Validaciones y Protecciones {#validaciones-y-protecciones}

### Anti-Disparo (Reconexión/Reset)

| Validación | Descripción | Acción |
|------------|-------------|--------|
| Gap de tiempo | Δt > 2 horas | Caudal = 0 |
| Días sin conexión | Registro anterior desconectado | Caudal = 0 |
| Consumo excesivo | > 500 m³/hora | Caudal = 0 |
| Caudal máximo | > 150 L/s | Caudal = 0 |
| Pulsos negativos | < 0 | Mantener último válido |
| Salto masivo | Diff > 500 m³ | Bloquear, mantener anterior |
| Glitch (cero) | Pulsos = 0 repentino | Ignorar valor |
| Reset real | 0 < actual < anterior | Actualizar addition |

### Validaciones de Rango

```python
# En process_variable_safely
if min_val is not None and current_val < float(min_val):
    return  # Ignorar valor

if max_val is not None and current_val > float(max_val):
    return  # Ignorar valor
```

### Validación de Fórmulas

```python
# En FormulaEngine.evaluate
if not re.match(r'^[0-9\.\+\-\*\/\(\)\s]+$', processed):
    return 0.0  # Caracteres inválidos

# Namespace restringido (sin __builtins__)
namespace = {'__builtins__': {}, 'abs': abs, 'min': min, ...}
```

---

## 📊 Resumen de Funciones {#resumen-de-funciones}

### FormulaEngine

| Función | Propósito | Retorno |
|---------|-----------|---------|
| `__init__(point_id)` | Inicializa motor | - |
| `evaluate(formula, values, ts)` | Evalúa fórmula | float |
| `process_variable(var, raw, values, ts)` | Procesa variable | float |
| `get_formula_for_variable(var, values, ts)` | Obtiene fórmula | str/None |
| `_load_context()` | Carga contexto | - |
| `_load_previous_values(ts)` | Valores previos | dict |
| `_load_time_context(ts, prev_ts)` | Contexto temporal | dict |
| `_replace_tokens(formula, values)` | Reemplaza tokens | str |

### Controladores Unificados

| Función | Propósito | Retorno |
|---------|-----------|---------|
| `save_telemetry_data(point_id, register, vars)` | Guarda registro | TelemetryRecord |
| `get_data_with_retry(func, *args)` | Retry con backoff | dict/None |
| `log_variable_processing(...)` | Logging estructurado | - |
| `validate_frequency(point, time)` | Valida frecuencia DGA | bool |
| `process_totalizado_variable(...)` | Procesa TOTALIZADO | tuple |
| `process_nivel_variable(...)` | Procesa NIVEL | dict |
| `process_caudal_variable(...)` | Procesa CAUDAL | dict |
| `process_caudal_promedio_variable(...)` | Procesa CAUDAL_PROMEDIO | dict |
| `process_variable_safely(...)` | Procesa con fallback | tuple |
| `calculate_days_not_connection(...)` | Días sin conexión | dict |
| `determine_dga_send(point, tz)` | Determina envío DGA | bool |

### Procesadores Legacy

| Función | Archivo | Propósito |
|---------|---------|-----------|
| `instantaneous_flow(...)` | flow.py | Caudal instantáneo |
| `average_flow(...)` | flow.py | Caudal promedio |
| `total_m3(...)` | total.py | Total con reset |
| `total_hour(...)` | total.py | Diff por hora |
| `total_day(...)` | total.py | Acumulado día |
| `nivel_mt(...)` | nivel.py | Nivel en metros |
| `water_table(...)` | nivel.py | Nivel freático |

### ConfigService

| Función | Propósito | Retorno |
|---------|-----------|---------|
| `get(key, default)` | Obtiene configuración | Any |
| `get_int(key, default)` | Obtiene como int | int |
| `get_float(key, default)` | Obtiene como float | float |
| `get_bool(key, default)` | Obtiene como bool | bool |
| `set(key, value, ...)` | Establece configuración | SystemConfiguration |
| `initialize_defaults()` | Inicializa defaults | dict |
| `clear_cache(key)` | Limpia cache | - |

---

## 🔄 Migración Legacy → Dinámico

### Estado Actual

El sistema soporta **ambos modos**:

1. **FormulaEngine (Nuevo)**: Prioridad si existe CoreVariable con `type_definition` o `formula`
2. **Procesadores Legacy (Fallback)**: Si FormulaEngine no está disponible

### Cómo Migrar

1. **Crear VariableType** con fórmula por defecto:
```python
VariableType.objects.create(
    code='TOTALIZADO',
    name='Totalizado',
    default_formula='({pulses} * {config.pulses_factor}) / 1000 + {config.addition}'
)
```

2. **Asignar a CoreVariable**:
```python
variable.type_definition = variable_type
variable.save()
```

3. **FormulaEngine tomará el control** automáticamente

---

## 📝 Notas Finales

### Ventajas del Sistema Dinámico

1. **Flexibilidad**: Fórmulas configurables desde BD
2. **Reutilización**: VariableType define fórmulas por defecto
3. **Override**: CoreVariable puede sobrescribir fórmula
4. **Extensibilidad**: Nuevos tokens disponibles
5. **Auditoría**: Todo configurable desde admin

### Limitaciones Actuales

1. No soporta condicionales complejos (if/else)
2. No soporta funciones matemáticas avanzadas (sin, cos, etc.)
3. Namespace limitado por seguridad

### Mejoras Futuras Sugeridas

1. Agregar más funciones matemáticas al namespace
2. Soporte para expresiones condicionales
3. Validación de fórmulas en admin antes de guardar
4. Cache de fórmulas compiladas para performance

---

**Análisis realizado por:** Claude Sonnet 4.5  
**Fecha:** 2026-01-20 16:00 UTC-3
