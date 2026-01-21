# 📊 Esquema Completo del Sistema de Telemetría - Estado Actual

**Fecha:** 2026-01-20
**Versión:** V3 Dinámica y Unificada

---

## 🏗️ Arquitectura General

```
┌─────────────────────────────────────────────────────────────────┐
│                    SISTEMA DE TELEMETRÍA V3                      │
│                     (100% Dinámico y Configurable)               │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   INGESTA    │───▶│ PROCESAMIENTO│───▶│ ALMACENAMIENTO│
│  (Entrada)   │    │ (Transform)   │    │   (Salida)    │
└──────────────┘    └──────────────┘    └──────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
  4 Fuentes         3 Módulos            TelemetryRecord
   - API REST        - Caudal              (JSONField)
   - MQTT            - Nivel                    │
   - Providers       - Totalizado               │
   - Celery Tasks    + FormulaEngine            ▼
                                         ┌──────────────┐
                                         │  COMPLIANCE  │
                                         │  - DGA       │
                                         │  - SMA       │
                                         └──────────────┘
```

---

## 📁 Estructura de Directorios

```
api/telemetry/
├── models/                           # 🗄️ MODELOS DE DATOS
│   ├── catchment_points.py          # CatchmentPoint (Puntos de captación)
│   ├── telemetry.py                 # TelemetryRecord (Registros V3)
│   ├── configuration.py             # Esquemas de configuración
│   ├── constants_system.py          # Constantes del sistema
│   ├── granular_telemetry.py        # Datos granulares
│   └── management_super.py          # Configuración global
│
├── providers/                        # 🔌 SISTEMA DE PROVEEDORES DINÁMICO
│   ├── models.py                    # TelemetryProvider, CatchmentPointProvider
│   ├── handlers.py                  # DynamicAPIHandler (conectores)
│   ├── manager.py                   # ProviderManager (orquestador)
│   ├── mqtt_handler.py              # MQTT client dinámico
│   ├── mqtt_parser.py               # Parser de payloads MQTT
│   ├── mqtt_subscriber_service.py   # Servicio MQTT en tiempo real
│   ├── mqtt_models.py               # Modelos MQTT
│   ├── compliance_models.py         # ComplianceProvider, PointComplianceConfig
│   └── compliance_standard.py       # Estándares de compliance (DGA, SMA)
│
├── ingestion/                        # 📥 INGESTA Y PROCESAMIENTO
│   └── controllers/
│       ├── unified_processing.py    # save_telemetry_data() [FUNCIÓN CENTRAL]
│       └── processing/              # Módulos de procesamiento modular
│           ├── caudal.py            # process_caudal_variable()
│           ├── nivel.py             # process_nivel_variable()
│           ├── totalized.py         # process_totalizado_variable()
│           └── utils.py             # Utilidades compartidas
│
├── processing/                       # 🧮 MOTOR DE CÁLCULOS
│   └── formula_engine.py            # FormulaEngine (fórmulas dinámicas)
│
├── services/                         # 🔧 SERVICIOS DE NEGOCIO
│   ├── telemetry_service.py         # Lógica de telemetría
│   └── compliance_service.py        # Servicio de compliance
│
├── validators/                       # ✅ VALIDADORES
│   └── telemetry_validator.py       # Validación y coherencia de datos
│
├── utils/                            # 🛠️ UTILIDADES
│   ├── caudal_calculations.py       # Cálculos de caudal
│   └── flow_display.py              # Display de flujos
│
├── management/commands/              # 🎮 COMANDOS DJANGO
│   └── mqtt_subscriber.py           # python manage.py mqtt_subscriber
│
└── admin.py                          # 👨‍💼 Django Admin personalizado
```

---

## 🗄️ MODELOS DE DATOS (Base de Datos)

### 1. CatchmentPoint (Punto de Captación)

**Descripción:** Representa un punto de medición (pozo, cauce, estación).

```python
CatchmentPoint
├─ id: int
├─ title: str                    # Nombre del punto
├─ point_code: str               # Código único
├─ project: FK(Project)          # Proyecto asociado
├─ owner_user: FK(User)          # Propietario
├─ lat, lon: float               # Coordenadas GPS
├─ frecuency: str                # "1", "5", "10", "60" minutos
├─ processing_scheme: FK(TelemetryScheme)      # Plantilla de procesamiento
├─ configuration_scheme: FK(ConfigurationScheme) # Config específica
├─ is_active: bool
└─ created, updated: datetime
```

**Funcionalidades:**

- ✅ Configuración de frecuencia de muestreo
- ✅ Asignación de esquemas de procesamiento reutilizables
- ✅ Geolocalización
- ✅ Multi-tenant (por proyecto)

---

### 2. TelemetryRecord (Registro de Telemetría V3)

**Descripción:** Almacena datos de telemetría de forma **100% dinámica** usando JSON.

```python
TelemetryRecord
├─ id: int
├─ point: FK(CatchmentPoint)     # [INDEXED]
├─ timestamp: DateTime           # [INDEXED]
├─ data: JSONField               # ⭐ DATOS DINÁMICOS
│   ├─ "flow": 12.5              # Caudal (L/s)
│   ├─ "nivel": 3.2              # Nivel (m)
│   ├─ "total": 1500             # Volumen acumulado (m³)
│   ├─ "caudal_promedio": 12.3   # Promedio calculado
│   ├─ "consumo_diario": 45.2    # Consumo (m³)
│   └─ [cualquier variable custom]
│
├─ metadata: JSONField           # Info del dispositivo
│   ├─ "provider": "Twin API"
│   ├─ "device_id": "sensor_001"
│   ├─ "processing_time_ms": 45
│   └─ "partial": false
│
├─ compliance_status: JSONField  # Estado de envío
│   ├─ "dga": {"sent": true, "voucher": "DGA123", "timestamp": "..."}
│   ├─ "sma": {"sent": false}
│   └─ [otros proveedores]
│
├─ is_error: bool                # [INDEXED]
├─ is_partial: bool              # [INDEXED]
└─ created_at: DateTime
```

**Ventajas del modelo V3:**

- ✅ **Sin esquema fijo**: Soporta cualquier número de variables
- ✅ **No requiere migraciones**: Agregar nuevas variables es instantáneo
- ✅ **Multi-compliance**: Soporta múltiples servicios (DGA, SMA, etc.)
- ✅ **Optimizado**: Índices en point_id, timestamp, is_error

---

### 3. CoreVariable (Variable Configurada)

**Descripción:** Define las variables que se procesan para cada punto.

```python
CoreVariable
├─ point: FK(CatchmentPoint)
├─ internal_code: str            # "flow", "nivel", "total", "custom_var"
├─ name: str                     # "Caudal Instantáneo"
├─ unit: str                     # "L/s", "m", "m³"
├─ type_variable: str            # TOTALIZADO|NIVEL|CAUDAL|CAUDAL_PROMEDIO|GENERIC
├─ operation: str                # PHYSICAL|SUM|DIFF|MUL|AVG|FORMULA
├─ formula: str                  # "{var1} + {var2}" (si operation=FORMULA)
├─ sources: JSONField            # ["var1", "var2"] (variables de origen)
├─ scale_factor: float           # Factor de escala (default: 1.0)
├─ offset: float                 # Offset (default: 0.0)
├─ min_value, max_value: float   # Validación de rangos
├─ provider_key: str             # "caudal_l_s" (key en API del proveedor)
├─ priority: int                 # Orden de cálculo (para dependencias)
├─ is_virtual: bool              # ¿Es calculada o física?
└─ is_active: bool
```

**Tipos de variables:**

- 🌊 **CAUDAL**: Flujo instantáneo (L/s)
- 📏 **NIVEL**: Profundidad freática (m)
- 📊 **TOTALIZADO**: Pulsos → Volumen (m³)
- 📈 **CAUDAL_PROMEDIO**: Promedio dinámico
- 🔧 **GENERIC**: Sin transformación especial

**Operaciones:**

- **PHYSICAL**: Valor directo del sensor
- **SUM**: Suma de variables
- **DIFF**: Diferencia
- **MUL**: Multiplicación
- **AVG**: Promedio
- **FORMULA**: Expresión matemática libre

---

### 4. TelemetryProvider (Proveedor de Datos)

**Descripción:** Define proveedores de telemetría (Twin, Novus, Nettra, MQTT).

```python
TelemetryProvider
├─ name: str                     # "twin", "novus", "nettra"
├─ display_name: str             # "Twin Hidro"
├─ provider_type: str            # "api" | "mqtt" | "modbus"
├─ base_url: str                 # https://api.twin.cl
├─ auth_method: str              # "bearer" | "basic" | "oauth2"
├─ auth_config: JSONField        # {"token": "...", "refresh_url": "..."}
├─ endpoint_template: str        # "/devices/{device_id}/data"
├─ request_template: JSONField   # Plantilla de request
├─ response_mapping: JSONField   # Mapeo de respuesta
├─ default_config: JSONField     # Config por defecto
└─ is_active: bool
```

**Proveedores soportados:**

- ✅ **Twin Hidro** (API REST)
- ✅ **Novus** (MQTT)
- ✅ **Nettra** (API REST)
- ✅ **MQTT Genérico** (Configurable)
- ✅ **Cualquier proveedor nuevo** (sin código)

---

### 5. CatchmentPointProvider (Configuración por Punto)

**Descripción:** Asocia un punto con un proveedor y su configuración.

```python
CatchmentPointProvider
├─ point: FK(CatchmentPoint)
├─ provider: FK(TelemetryProvider)
├─ config_data: JSONField        # Config específica del punto
│   ├─ "device_id": "sensor_123"
│   ├─ "token": "abc123..."
│   ├─ "custom_endpoint": "/v2/data"
│   └─ [cualquier config]
├─ is_active: bool
└─ created_at: DateTime
```

---

### 6. ComplianceProvider (Proveedor de Compliance)

**Descripción:** Define servicios de cumplimiento regulatorio (DGA, SMA, INDH).

```python
ComplianceProvider
├─ name: str                     # "dga", "sma", "indh"
├─ display_name: str             # "Dirección General de Aguas"
├─ auth_method: str              # "bearer" | "basic" | "oauth2"
├─ base_url: str                 # https://api.dga.cl
├─ endpoint_template: str        # "/ufs/{uf_id}/procesos/{id}/registros"
├─ payload_template: JSONField   # Plantilla de payload
├─ credentials: JSONField        # Credenciales (encriptadas)
└─ is_active: bool
```

**Servicios de compliance soportados:**

- ✅ **DGA** (Dirección General de Aguas)
- ⏳ **SMA** (Superintendencia del Medio Ambiente) - En proceso de migración
- 🔜 **INDH** (Instituto Nacional de Derechos Humanos)

---

### 7. PointComplianceConfig (Configuración de Compliance por Punto)

**Descripción:** Configura cómo se envía la telemetría de un punto a un servicio de compliance.

```python
PointComplianceConfig
├─ point: FK(CatchmentPoint)
├─ provider: FK(ComplianceProvider)
├─ is_active: bool
├─ send_compliance: bool         # ¿Enviar automáticamente?
├─ standard: str                 # "DAILY" | "WEEKLY" | "MONTHLY"
├─ config_data: JSONField        # Config específica
│   ├─ "uf_id": "123"
│   ├─ "process_id": "456"
│   ├─ "device_id": "789"
│   └─ [custom]
├─ last_submitted: DateTime      # Último envío
├─ voucher: str                  # Comprobante
└─ created_at: DateTime
```

---

## 🔌 SISTEMA DE PROVEEDORES DINÁMICO

### ProviderManager (Orquestador)

**Ubicación:** `api/telemetry/providers/manager.py`

**Función principal:**

```python
ProviderManager.get_data_with_provider(point_id, date_time=None)
```

**Flujo:**

```
1. Obtiene CatchmentPointProvider del punto
2. Carga TelemetryProvider
3. Construye request dinámicamente
4. Autentica según auth_method
5. Hace llamada a API
6. Mapea respuesta según response_mapping
7. Retorna datos normalizados
```

**Ejemplo de uso:**

```python
from api.telemetry.providers.manager import ProviderManager

# Obtener datos de cualquier proveedor
data = ProviderManager.get_data_with_provider(
    point_id=123,
    date_time=datetime.now()
)
# Retorna: {"flow": 12.5, "nivel": 3.2, "total": 1500, ...}
```

---

### DynamicAPIHandler (Conector HTTP)

**Ubicación:** `api/telemetry/providers/handlers.py`

**Características:**

- ✅ Soporta múltiples métodos de autenticación
- ✅ Templates de URL dinámicos
- ✅ Mapeo de respuesta configurable
- ✅ Retry con backoff exponencial
- ✅ Timeout configurable

**Métodos de autenticación:**

- `bearer`: Token Bearer en header
- `basic`: Basic Auth
- `oauth2`: OAuth2 flow
- `custom_header`: Headers personalizados

---

### MQTT Subscriber Service

**Ubicación:** `api/telemetry/providers/mqtt_subscriber_service.py`

**Comando:**

```bash
python manage.py mqtt_subscriber
```

**Funcionalidades:**

- ✅ Subscripción dinámica a topics MQTT
- ✅ Parser de payloads configurable
- ✅ Procesamiento en tiempo real
- ✅ Retry automático en errores
- ✅ Multi-broker (puede conectarse a varios brokers)

**Modelos de configuración:**

- `CatchmentPointMQTT`: Config MQTT por punto
- `MQTTProviderConfig`: Config del proveedor MQTT
- `PayloadParsingRule`: Reglas de parsing de payload

---

## 📥 INGESTA DE DATOS

### 4 Fuentes de Ingesta

#### 1. API REST (Manual o Externa)

**Endpoints:**

```
POST /api/telemetry/record/  # Crear registro manual
GET  /api/v2/telemetry/batch/ # Obtener registros en batch
```

#### 2. MQTT (Tiempo Real)

**Servicio:**

```bash
python manage.py mqtt_subscriber
```

**Flujo:**

```
MQTT Broker → MQTTSubscriberService → MQTTPayloadParser →
process_variable_safely() → save_telemetry_data() → TelemetryRecord
```

#### 3. Proveedores Dinámicos (APIs Externas)

**Proveedores:**

- Twin Hidro
- Novus
- Nettra
- Cualquier API REST configurable

**Flujo:**

```
ProviderManager → DynamicAPIHandler → API Externa →
Mapeo de respuesta → process_variable_safely() → save_telemetry_data()
```

#### 4. Celery Tasks (Ingesta Programada)

**Ubicación:** `api/core/tasks/telemetry.py`

**Tasks:**

```python
# Recolección automática cada N minutos
collect_telemetry.delay("1")   # Cada 1 minuto
collect_telemetry.delay("5")   # Cada 5 minutos
collect_telemetry.delay("10")  # Cada 10 minutos
collect_telemetry.delay("60")  # Cada 60 minutos
```

**Configuración Celery Beat:**

```python
CELERY_BEAT_SCHEDULE = {
    'collect-telemetry-1min': {
        'task': 'api.core.tasks.telemetry.collect_telemetry',
        'schedule': crontab(minute='*/1'),
        'args': ('1',)
    },
    # ...
}
```

---

## 🧮 PROCESAMIENTO DE DATOS

### Función Central: `save_telemetry_data()`

**Ubicación:** `api/telemetry/ingestion/controllers/unified_processing.py`

**Firma:**

```python
def save_telemetry_data(
    point_id: int,
    created_register: datetime,
    processed_variables: Dict[str, Any]
) -> TelemetryRecord
```

**Flujo de procesamiento:**

```
1. VALIDAR ENTRADA
   └─ Verificar point_id existe
   └─ Validar timestamp

2. PROCESAR VARIABLES
   └─ Para cada variable en processed_variables:
      ├─ Detectar tipo (TOTALIZADO|NIVEL|CAUDAL|etc)
      ├─ Aplicar procesamiento específico
      ├─ Aplicar scale_factor + offset
      └─ Validar rangos (min/max)

3. APLICAR FÓRMULAS DINÁMICAS
   └─ FormulaEngine.evaluate(formula, variables)

4. CREAR REGISTRO
   └─ TelemetryRecord.objects.create(
       point=point,
       timestamp=created_register,
       data=processed_variables,
       metadata={...},
       compliance_status={}
   )

5. RETORNAR REGISTRO
```

---

### Módulos de Procesamiento Modular

#### 1. Procesamiento de Caudal

**Archivo:** `api/telemetry/ingestion/controllers/processing/caudal.py`

**Funciones:**

```python
process_caudal_variable(value, variable_config)
# Procesa caudal instantáneo (L/s)
# Aplica: value * scale_factor + offset

process_caudal_promedio_variable(point_id, variable_config, window_minutes=60)
# Calcula promedio de caudal de últimos N minutos
# Retorna: promedio ponderado
```

**Tipos:**

- `CAUDAL`: Flujo instantáneo
- `CAUDAL_PROMEDIO`: Promedio móvil

---

#### 2. Procesamiento de Nivel

**Archivo:** `api/telemetry/ingestion/controllers/processing/nivel.py`

**Funciones:**

```python
process_nivel_variable(value, variable_config)
# Procesa profundidad freática (m)
# Corrección de valores negativos
# Cálculo de nivel freático

nivel_mt(value, d1, d2)
# Convierte a metros según profundidad

water_table(nivel, d1)
# Calcula nivel freático
# water_table = d1 - nivel
```

---

#### 3. Procesamiento de Totalizado

**Archivo:** `api/telemetry/ingestion/controllers/processing/totalized.py`

**Funciones:**

```python
process_totalizado_variable(pulses, variable_config)
# Convierte pulsos a volumen (m³)
# Fórmula: (pulses × factor) ÷ 1000
# Detecta resets de contador
# Calcula diferencias (consumo)
```

**Cálculos adicionales:**

- `total_diff`: Consumo desde último registro
- Detección de resets (cuando total < total_anterior)

---

### FormulaEngine (Motor de Fórmulas)

**Ubicación:** `api/telemetry/processing/formula_engine.py`

**Funciones:**

```python
FormulaEngine.evaluate(formula: str, variables: Dict) -> float
# Evalúa expresión matemática con variables
# Ejemplo: "{flow} * 3.6" con variables={"flow": 12.5} → 45.0

FormulaEngine.parse_formula(formula: str) -> List[str]
# Extrae variables usadas
# Ejemplo: "{flow} + {nivel}" → ["flow", "nivel"]

FormulaEngine.validate_formula(formula: str) -> Tuple[bool, str]
# Valida sintaxis y seguridad
```

**Operadores soportados:**

- Aritméticos: `+`, `-`, `*`, `/`, `%`, `**`
- Funciones: `sqrt()`, `abs()`, `round()`, `min()`, `max()`
- Paréntesis: `(`, `)`

**Ejemplo:**

```python
formula = "({caudal} * 3.6) + {offset}"
variables = {"caudal": 12.5, "offset": 2.0}
result = FormulaEngine.evaluate(formula, variables)
# result = 47.0
```

---

## 💾 ALMACENAMIENTO

### Estructura de TelemetryRecord.data

**Formato JSON dinámico:**

```json
{
  "flow": 12.5,              // Caudal instantáneo (L/s)
  "nivel": 3.2,              // Nivel (m)
  "total": 1500,             // Volumen acumulado (m³)
  "total_diff": 2.5,         // Consumo desde último registro (m³)
  "caudal_promedio": 12.3,   // Promedio de caudal (L/s)
  "water_table": 45.8,       // Nivel freático (m)
  "consumo_diario": 60.0,    // Consumo del día (m³)
  "custom_var_1": 100,       // Cualquier variable custom
  "temperatura": 25.5        // Otro ejemplo
}
```

### Índices de Base de Datos

**TelemetryRecord:**

```sql
CREATE INDEX idx_telemetry_point_timestamp ON telemetry_record(point_id, timestamp DESC);
CREATE INDEX idx_telemetry_error ON telemetry_record(is_error);
CREATE INDEX idx_telemetry_partial ON telemetry_record(is_partial);
CREATE INDEX idx_telemetry_compliance_dga ON telemetry_record((compliance_status->'dga'->'sent'));
```

**Ventajas:**

- ✅ Búsquedas rápidas por punto + timestamp
- ✅ Filtrado eficiente de errores
- ✅ Queries optimizadas de compliance

---

## ✅ COMPLIANCE (Cumplimiento Regulatorio)

### Servicio de Compliance

**Ubicación:** `api/telemetry/services/compliance_service.py`

**Funciones principales:**

```python
submit_telemetry_record(record_id, provider_name)
# Envía un registro a un proveedor de compliance

collect_records_to_submit(point_id, provider_name, start_date, end_date)
# Recolecta registros pendientes de envío

bulk_submit(point_ids, provider_name, start_date, end_date)
# Envío masivo
```

**Flujo de envío:**

```
1. Obtener PointComplianceConfig
2. Verificar should_submit_now()
3. Construir payload según ComplianceProvider.payload_template
4. Autenticar
5. POST a ComplianceProvider.base_url + endpoint
6. Actualizar TelemetryRecord.compliance_status
7. Guardar voucher
```

---

### Proveedores de Compliance Activos

#### 1. DGA (Dirección General de Aguas)

**Estado:** ✅ Activo y funcionando

**Estándares:**

- `DAILY`: Envío diario
- `WEEKLY`: Envío semanal
- `MONTHLY`: Envío mensual

**Configuración por punto:**

```python
PointComplianceConfig.objects.create(
    point=punto,
    provider=dga_provider,
    is_active=True,
    send_compliance=True,
    standard="DAILY",
    config_data={
        "uf_id": "123",
        "process_id": "456",
        "code_dga": "ND-0101-123"
    }
)
```

**Task Celery:**

```python
# api/core/tasks/dga.py
submit_dga_records.delay()  # Envío automático
```

---

#### 2. SMA (Superintendencia del Medio Ambiente)

**Estado:** ⏳ En proceso de migración a sistema dinámico

**Archivo actual:** `api/core/tasks/sma.py` (con hardcodes)

**Pendiente:**

- Migrar a ComplianceProvider
- Configurar desde BD
- Eliminar hardcodes (usuario, password, device_id)

---

## 🎮 COMANDOS Y TASKS

### Comandos Django

```bash
# MQTT Subscriber
python manage.py mqtt_subscriber
# Inicia servicio MQTT en tiempo real

# Validar implementación
python manage.py validate_telemetry_implementation
# Verifica que todo esté configurado correctamente
```

---

### Celery Tasks

**Ubicación:** `api/core/tasks/`

#### Telemetría

```python
# api/core/tasks/telemetry.py

collect_telemetry.delay("1")    # Recolectar frecuencia 1 min
collect_telemetry.delay("5")    # Recolectar frecuencia 5 min
collect_telemetry.delay("10")   # Recolectar frecuencia 10 min
collect_telemetry.delay("60")   # Recolectar frecuencia 60 min

process_telemetry_batch.delay(batch_ids)  # Procesar batch en paralelo
process_single_point_unified.delay(point_id, date_time)  # Procesar un punto
```

#### Compliance

```python
# api/core/tasks/compliance.py
submit_compliance.delay(point_id, provider_name)

# api/core/tasks/dga.py
submit_dga_records.delay()  # Envío automático DGA

# api/core/tasks/sma.py
process_sma_queue.delay()   # Procesar cola SMA
```

#### Monitoreo

```python
# api/core/tasks/monitoring.py
check_data_quality.delay()           # Verificar calidad de datos
detect_anomalies.delay(point_id)     # Detectar anomalías
```

---

## 📊 APIs REST Disponibles

### Endpoints V2 (Optimizados)

```
GET  /api/v2/dashboard/summary/
# Dashboard ejecutivo con métricas generales

GET  /api/v2/dashboard/realtime/
# Dashboard en tiempo real

GET  /api/v2/telemetry/batch/
# Obtener telemetría en batch
# Params: point_ids, start_date, end_date, variables

GET  /api/v2/telemetry/export/
# Exportar datos (CSV/JSON)
```

---

### Endpoints de Proveedores

```
GET    /api/providers/
# Listar proveedores disponibles

GET    /api/providers/{name}/
# Detalles de un proveedor

GET    /api/providers/{name}/test/
# Probar conexión con proveedor

POST   /api/providers/points/{id}/
# Configurar proveedor para un punto

POST   /api/providers/points/{id}/data/fetch/
# Obtener datos del proveedor ahora
```

---

### Endpoints de Compliance

```
GET    /api/compliance/providers/
# Listar proveedores de compliance

POST   /api/compliance/submit/{point_id}/{provider}/
# Enviar registro a compliance

GET    /api/compliance/status/{point_id}/
# Estado de compliance del punto
```

---

## 🔍 VALIDADORES Y ANÁLISIS

### TelemetryValidator

**Ubicación:** `api/telemetry/validators/telemetry_validator.py`

**Funciones:**

```python
analyze_data_coherence(point_id, days_back=30)
# Analiza coherencia de datos de un punto
# Detecta:
# - Outliers (valores atípicos)
# - Gaps de datos
# - Valores imposibles
# - Tendencias anómalas

calculate_max_flow_by_diameter(diameter_mm)
# Calcula caudal máximo físicamente posible

validate_telemetry_record(record)
# Valida un registro individual
```

**Retorna:**

```python
{
    "status": "ok" | "warning" | "error",
    "total_records": 1440,
    "outliers": 12,
    "gaps": [
        {"start": "2026-01-15", "end": "2026-01-16", "duration_hours": 24}
    ],
    "impossible_values": [
        {"timestamp": "...", "variable": "flow", "value": 999, "max_allowed": 50}
    ],
    "quality_score": 95.5
}
```

---

## 🎯 FUNCIONALIDADES PRINCIPALES

### ✅ Funcionalidades Implementadas

#### 1. Ingesta Multi-Fuente

- ✅ API REST (manual o externa)
- ✅ MQTT en tiempo real
- ✅ Proveedores dinámicos (Twin, Novus, Nettra)
- ✅ Celery Tasks programadas

#### 2. Procesamiento Dinámico

- ✅ Caudal (instantáneo y promedio)
- ✅ Nivel (con corrección y cálculo de nivel freático)
- ✅ Totalizado (pulsos a volumen con detección de resets)
- ✅ Fórmulas personalizadas (FormulaEngine)
- ✅ Variables derivadas automáticas

#### 3. Almacenamiento Flexible

- ✅ JSONField para datos dinámicos
- ✅ Sin esquema fijo (sin migraciones para nuevas variables)
- ✅ Metadata de procesamiento
- ✅ Estado de compliance por registro

#### 4. Compliance Regulatorio

- ✅ DGA (automático)
- ⏳ SMA (en migración)
- ✅ Sistema extensible para nuevos proveedores

#### 5. Validación y Calidad

- ✅ Detección de outliers
- ✅ Validación de rangos
- ✅ Análisis de coherencia
- ✅ Métricas de calidad de datos

#### 6. Sistema de Proveedores

- ✅ Configuración 100% desde BD
- ✅ Sin código para agregar proveedores
- ✅ Multi-tenant
- ✅ Autenticación flexible

---

### 🚀 Ventajas del Sistema Actual

1. **100% Dinámico**
   - No requiere código para agregar variables
   - No requiere migraciones de BD
   - Configuración completa desde Django Admin

2. **Escalable**
   - Procesamiento en paralelo con Celery
   - Batching automático
   - Índices optimizados

3. **Multi-Tenant**
   - Soporta múltiples proyectos
   - Configuración independiente por punto
   - Aislamiento de datos

4. **Extensible**
   - Nuevos proveedores sin código
   - Nuevos servicios de compliance sin código
   - Sistema de plugins

5. **Robusto**
   - Retry automático
   - Manejo de errores
   - Validación de datos
   - Logging estructurado

---

## 📈 Casos de Uso

### Caso 1: Agregar un Nuevo Punto de Captación

```python
# 1. Crear punto
punto = CatchmentPoint.objects.create(
    title="Pozo Nuevo 1",
    point_code="PZ-001",
    project=proyecto,
    lat=-33.4372,
    lon=-70.6506,
    frecuency="5"  # Cada 5 minutos
)

# 2. Configurar proveedor
CatchmentPointProvider.objects.create(
    point=punto,
    provider=TelemetryProvider.objects.get(name="twin"),
    config_data={
        "device_id": "sensor_123",
        "token": "abc123..."
    }
)

# 3. Configurar variables
CoreVariable.objects.create(
    point=punto,
    internal_code="flow",
    name="Caudal Instantáneo",
    unit="L/s",
    type_variable="CAUDAL",
    operation="PHYSICAL",
    scale_factor=1.0
)

# 4. Configurar compliance DGA
PointComplianceConfig.objects.create(
    point=punto,
    provider=ComplianceProvider.objects.get(name="dga"),
    is_active=True,
    send_compliance=True,
    standard="DAILY",
    config_data={
        "uf_id": "123",
        "process_id": "456"
    }
)

# ¡Listo! El sistema empezará a recolectar datos automáticamente
```

---

### Caso 2: Crear Variable Calculada

```python
# Crear variable de consumo diario
CoreVariable.objects.create(
    point=punto,
    internal_code="consumo_diario",
    name="Consumo Diario",
    unit="m³",
    type_variable="GENERIC",
    operation="FORMULA",
    formula="{total_fin_dia} - {total_inicio_dia}",
    sources=["total_fin_dia", "total_inicio_dia"],
    is_virtual=True
)
```

---

### Caso 3: Obtener Datos Desde el Código

```python
from api.telemetry.models import TelemetryRecord
from datetime import datetime, timedelta

# Obtener últimos registros
registros = TelemetryRecord.objects.filter(
    point_id=123,
    timestamp__gte=datetime.now() - timedelta(days=7)
).order_by('-timestamp')

for registro in registros:
    print(f"Timestamp: {registro.timestamp}")
    print(f"Caudal: {registro.data.get('flow')} L/s")
    print(f"Nivel: {registro.data.get('nivel')} m")
    print(f"Total: {registro.data.get('total')} m³")
    print(f"DGA enviado: {registro.compliance_status.get('dga', {}).get('sent')}")
```

---

## 🔧 Configuración desde Django Admin

### Acceso al Admin

```
URL: https://tu-dominio.com/admin/
```

### Secciones disponibles

1. **Telemetría**
   - Puntos de Captación (CatchmentPoint)
   - Registros de Telemetría (TelemetryRecord)
   - Variables (CoreVariable)
   - Esquemas de Procesamiento (TelemetryScheme)

2. **Proveedores**
   - Proveedores de Telemetría (TelemetryProvider)
   - Configuración por Punto (CatchmentPointProvider)
   - Proveedores MQTT (MQTTProviderConfig)

3. **Compliance**
   - Proveedores de Compliance (ComplianceProvider)
   - Configuración por Punto (PointComplianceConfig)

---

## 📝 Resumen Ejecutivo

### Estado Actual

- ✅ Sistema V3 100% funcional
- ✅ Ingesta multi-fuente operativa
- ✅ Procesamiento dinámico activo
- ✅ Compliance DGA automático
- ✅ MQTT en tiempo real funcionando
- ⏳ SMA en proceso de migración

### Eliminado Recientemente (2026-01-20)

- ❌ Módulo `api/reports/` (hardcodeado)
- ❌ Cronjobs legacy (reemplazados por Celery)
- ❌ Funciones de reportes en admin

### Próximos Pasos Recomendados

1. 🔜 Migrar SMA a sistema de compliance dinámico
2. 🔜 Crear nuevo sistema de reportes configurable
3. 🔜 Agregar más proveedores de compliance (INDH)
4. 🔜 Dashboard de analytics en tiempo real

---

## 🆘 Soporte y Documentación

### Archivos de Documentación

- `RESUMEN_APP_TELEMETRIA.md` - Resumen general
- `PROJECT_STRUCTURE.md` - Estructura del proyecto
- `api/telemetry/ANALISIS_OPERACIONES.md` - Análisis operacional
- `api/telemetry/GUIA_MQTT_SUBSCRIBER.md` - Guía MQTT
- `api/telemetry/IMPLEMENTACION_COMPLETA.md` - Estado de implementación
- `api/telemetry/VALIDACION_COMPLETA.md` - Validaciones

### Logs y Monitoreo

```bash
# Logs de Celery
docker logs celery_worker --tail=100

# Logs de Django
tail -f logs/django.log

# Monitoring con Flower
http://localhost:5555
```

---

**FIN DEL ESQUEMA**
