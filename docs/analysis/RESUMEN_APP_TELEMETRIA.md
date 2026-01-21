# 📊 RESUMEN SIMPLE: App Telemetría

**¿Te parece confuso?** Te explico la arquitectura de forma simple y clara.

---

## 🎯 ¿Qué hace esta app?

**En una frase:** Recolecta datos de sensores IoT (caudal, nivel, volumen) desde múltiples fuentes (APIs, MQTT) y los procesa, valida y envía a organismos reguladores (DGA, SMA).

---

## 📂 Estructura Principal (simplificada)

```
api/telemetry/
│
├── 📁 models/                    # ¿QUÉ datos guardamos?
│   ├── catchment_points.py      → Puntos de monitoreo (pozos, cauces)
│   ├── telemetry.py             → Registros de telemetría + Variables
│   └── configuration.py         → Configuraciones dinámicas
│
├── 📁 providers/                 # ¿DE DÓNDE vienen los datos?
│   ├── models.py                → Define proveedores (Twin, Novus, MQTT)
│   ├── handlers.py              → Conectores API/MQTT
│   ├── manager.py               → Enrutador que elige el mejor proveedor
│   ├── mqtt_handler.py          → Manejo de MQTT
│   └── compliance_models.py     → Proveedores de compliance (DGA, SMA)
│
├── 📁 ingestion/                 # ¿CÓMO procesamos los datos?
│   └── controllers/
│       └── unified_processing.py → Función central: save_telemetry_data()
│
├── 📁 processing/                # ¿CÓMO calculamos variables?
│   └── formula_engine.py        → Motor de fórmulas dinámicas
│
├── 📁 validators/                # ¿Cómo validamos calidad?
│   └── telemetry_validator.py   → Detecta valores imposibles
│
├── 📁 services/                  # ¿A DÓNDE enviamos los datos?
│   ├── compliance_service.py    → Envía a DGA, SMA, etc.
│   └── telemetry_service.py     → Lógica de negocio
│
└── 📁 admin*.py                  # Interfaces de administración Django
```

---

## 🔄 Flujo de Datos (Simplificado)

```
┌────────────────────────────────────────────────────────────────┐
│                     1. ORIGEN DE DATOS                         │
└────────────────────────────────────────────────────────────────┘
         │
         ├─→ Twin API (API REST cada 60 min) ───┐
         ├─→ Novus API (API REST cada 60 min) ──┤
         ├─→ Nettra API (API REST) ─────────────┤
         └─→ MQTT Broker (Tiempo real) ─────────┤
                                                 │
┌────────────────────────────────────────────────▼───────────────┐
│          2. PROVIDERS (Capa de Abstracción)                    │
│                                                                 │
│  ProviderManager selecciona el mejor proveedor para cada punto │
│  Handler correspondiente (API/MQTT) obtiene los datos          │
└────────────────────────────────────────────────┬───────────────┘
                                                 │
┌────────────────────────────────────────────────▼───────────────┐
│          3. PROCESSING (Cálculos y Transformaciones)           │
│                                                                 │
│  • FormulaEngine evalúa fórmulas dinámicas                     │
│  • Calibraciones (scale_factor, offset)                        │
│  • Cálculo de variables derivadas (caudal promedio, etc.)      │
└────────────────────────────────────────────────┬───────────────┘
                                                 │
┌────────────────────────────────────────────────▼───────────────┐
│          4. INGESTION (Guardado Unificado)                     │
│                                                                 │
│  save_telemetry_data() → TelemetryRecord en BD                 │
│  Formato: {"flow": 12.5, "nivel": 3.2, "total": 1500}         │
└────────────────────────────────────────────────┬───────────────┘
                                                 │
                         ┌───────────────────────┴────────────┐
                         │                                    │
┌────────────────────────▼───────────┐   ┌────────────────────▼──────────┐
│   5A. VALIDATION                   │   │   5B. COMPLIANCE               │
│                                    │   │                                │
│  • ¿Caudal imposible?              │   │  • ¿Enviar a DGA?             │
│  • ¿Nivel imposible?               │   │  • ¿Enviar a SMA?             │
│  • Análisis de coherencia          │   │  • Generación de reportes     │
└────────────────────────────────────┘   └───────────────────────────────┘
```

---

## 🗂️ Modelos Clave (Lo más importante)

### 1️⃣ **CatchmentPoint** (Punto de Captación)

**¿Qué es?** Un lugar físico donde hay un sensor (pozo, río, canal).

```python
CatchmentPoint
  ├─ title: "Pozo Norte"
  ├─ point_code: "PN-001"
  ├─ project: FK a proyecto
  ├─ configuration_scheme: Esquema de configuración (d1, d2, d3, etc.)
  ├─ sampling_frequency: Cada cuánto mide (1min, 5min, 60min)
  └─ providers: Qué proveedor usa (Twin, Novus, MQTT)
```

**Relaciones:**
- Tiene **muchas** variables (`CoreVariable`)
- Tiene **muchos** registros de telemetría (`TelemetryRecord`)
- Tiene **configuraciones** (`PointConfigurationValue`)
- Tiene **compliance configs** (`PointComplianceConfig`)

---

### 2️⃣ **TelemetryRecord** (Registro de Telemetría) ⭐ IMPORTANTE

**¿Qué es?** Un snapshot de datos en un momento específico.

```python
TelemetryRecord
  ├─ point: FK a CatchmentPoint
  ├─ timestamp: "2026-01-20 15:30:00"
  ├─ data: {                           # ← JSON dinámico
  │    "flow": 12.5,                   # Caudal en L/s
  │    "nivel": 3.2,                   # Nivel en metros
  │    "total": 1500.0,                # Total acumulado en m³
  │    "pulses": 1500000,              # Pulsos del contador
  │    "water_table": 2.8              # Nivel freático
  │  }
  ├─ metadata: {                       # Información adicional
  │    "device_id": "sensor_001",
  │    "provider": "twin",
  │    "processed_at": "2026-01-20 15:30:05"
  │  }
  ├─ send_dga: Boolean (¿enviar a DGA?)
  ├─ n_voucher: Número de comprobante DGA
  ├─ is_error: ¿Hay error en los datos?
  └─ is_partial: ¿Datos incompletos?
```

**¿Por qué es JSON y no columnas separadas?**
- ✅ **Flexible**: Cada punto puede tener variables diferentes
- ✅ **Escalable**: Agregar nuevas variables sin migrar BD
- ✅ **Dinámico**: No necesitas modificar modelos para nuevos sensores

---

### 3️⃣ **CoreVariable** (Variable Dinámica)

**¿Qué es?** Define qué medir en cada punto.

```python
CoreVariable
  ├─ point: FK a CatchmentPoint
  ├─ internal_code: "caudal_instantaneo"   # Clave única
  ├─ type_variable: "5000"                 # Código del proveedor
  ├─ operation: "FORMULA"                  # PHYSICAL, SUM, DIFF, FORMULA
  ├─ formula: "{pulses} * {config.factor} / 1000"  # Fórmula dinámica
  ├─ sources: ["pulses", "config.factor"]  # De qué depende
  ├─ scale_factor: 1.0                     # Calibración
  ├─ offset: 0.0                           # Ajuste
  ├─ min_value: 0.0                        # Validación mínima
  └─ max_value: 1000.0                     # Validación máxima
```

**Operaciones:**
- `PHYSICAL`: Lectura directa del sensor
- `SUM`: Suma de otras variables
- `DIFF`: Diferencia entre mediciones
- `FORMULA`: Evaluación con FormulaEngine

---

### 4️⃣ **TelemetryProvider** (Proveedor de Datos)

**¿Qué es?** Configuración de dónde vienen los datos.

```python
TelemetryProvider
  ├─ name: "twin"
  ├─ provider_type: "api"              # api, mqtt, modbus, http
  ├─ base_url: "https://api.twin.com.br"
  ├─ auth_method: "bearer"             # bearer, basic, api_key, oauth2
  ├─ auth_config: {
  │    "token": "Bearer xyz123..."
  │  }
  ├─ endpoint_template: "/device/{device_id}/telemetry"
  ├─ timeout_seconds: 30
  └─ max_retries: 3
```

**Tipos de proveedores:**
- **Twin**: API REST brasileña
- **Novus**: API REST argentina
- **Nettra**: API REST chilena
- **MQTT**: Broker local (devices publican directamente)

---

### 5️⃣ **ComplianceProvider** (Proveedor de Compliance)

**¿Qué es?** Configuración de organismos reguladores.

```python
ComplianceProvider
  ├─ name: "dga"
  ├─ display_name: "DGA - Dirección General de Aguas"
  ├─ base_url: "https://siac.mop.gob.cl/ufs"
  ├─ payload_template: {                # Template dinámico
  │    "codigo_obra": "{config.codigo_obra}",
  │    "caudal": "{record.data.flow}",
  │    "volumen": "{record.data.total}",
  │    "fecha": "{record.timestamp}"
  │  }
  ├─ submission_frequency: "hourly"     # realtime, hourly, daily, monthly
  └─ required_fields: [...]             # Campos obligatorios
```

---

## ⚙️ Componentes Críticos

### 🔧 **ProviderManager** (providers/manager.py)

**¿Qué hace?** Enrutador inteligente que selecciona el mejor proveedor.

```python
# Ejemplo de uso
manager = ProviderManager()

# Obtener proveedor para un punto
provider = manager.get_best_provider_for_point(point_id=123)

# Obtener handler (conector)
handler = manager.get_handler('twin')

# Obtener datos
data = handler.fetch_data(device_id='sensor_001', variable_type='5000')
```

**Lógica de selección:**
1. Busca `CatchmentPointProvider` activo para el punto
2. Ordena por `priority` (menor = más prioritario)
3. Instancia el handler correcto (API o MQTT)
4. Si falla, intenta con el siguiente proveedor

---

### 🧮 **FormulaEngine** (processing/formula_engine.py)

**¿Qué hace?** Evalúa fórmulas dinámicas con variables.

```python
# Ejemplo de fórmula
formula = "({pulses} * {config.pulses_factor}) / 1000"

# Variables disponibles:
# {var_code}          → Otras variables del punto
# {config.code}       → Configuración del punto (d1, d2, pulses_factor)
# {system.key}        → Configuración global
# {prev.var_code}     → Valor anterior de la variable
# {time.diff_seconds} → Tiempo desde última medición

# Ejemplo real:
# Caudal = (Total actual - Total anterior) / (tiempo transcurrido / 3600)
flow_formula = "({total} - {prev.total}) / ({time.diff_seconds} / 3600)"
```

**¿Por qué es importante?**
- ✅ No necesitas código para agregar nuevas variables calculadas
- ✅ Usuarios avanzados pueden crear fórmulas desde Django Admin
- ✅ Reemplaza archivos legacy hardcodeados (flow.py, nivel.py, total.py)

---

### 💾 **save_telemetry_data()** (ingestion/controllers/unified_processing.py)

**¿Qué hace?** Función CENTRAL que guarda telemetría.

```python
def save_telemetry_data(point_id, created_register):
    """
    1. Mapea datos a JSON: {"flow": 12.5, "total": 1500}
    2. Crea TelemetryRecord en BD
    3. Obtiene proveedores de compliance activos
    4. Encola tareas de envío asíncrono (Celery)
    5. Retorna el registro guardado
    """
```

**Todos los caminos llevan aquí:**
- Cronjob Twin → save_telemetry_data()
- Cronjob Novus → save_telemetry_data()
- MQTT Subscriber → save_telemetry_data()
- API POST → save_telemetry_data()

---

## 📥 Puntos de Entrada (¿De dónde vienen los datos?)

### 1️⃣ **Cronjobs Programados** (api/cronjobs/telemetry/)

**twin_dynamic.py**
```python
# Ejecuta cada 60 minutos
# Busca puntos con is_tdata=True, frecuency="60"
# Usa ProviderManager para obtener datos de Twin API
```

**novus_dynamic.py**
```python
# Ejecuta cada 60 minutos
# Busca puntos con is_novus=True, frecuency="60"
# Usa ProviderManager para obtener datos de Novus API
```

### 2️⃣ **MQTT Subscriber** (Tiempo Real)

**providers/mqtt_subscriber_service.py**
```python
# Servicio long-running que escucha broker MQTT
# Devices IoT publican directamente: mqtt/device_001/telemetry
# Parser extrae datos y llama save_telemetry_data()
```

**Cómo iniciar:**
```bash
python manage.py mqtt_subscriber start
```

### 3️⃣ **REST APIs** (providers/views.py)

- Webhooks para recibir datos por HTTP POST
- Endpoints personalizados por cliente

---

## 📤 Puntos de Salida (¿A dónde van los datos?)

### 1️⃣ **DGA (Dirección General de Aguas)**

**Flujo:**
```
TelemetryRecord guardado
  → should_submit_compliance('dga') valida frecuencia
    → send_compliance_data.delay() encola tarea Celery
      → ComplianceService.submit_telemetry_record()
        → POST a https://siac.mop.gob.cl/ufs/...
          → Recibe n_voucher (comprobante)
            → ComplianceSubmissionLog guardado
```

**Frecuencias de envío:**
- `realtime`: Cada registro (cada minuto)
- `hourly`: Solo en minuto 0 (ej: 15:00, 16:00)
- `daily`: Solo a las 00:00
- `monthly`: Día 1 a las 00:00

### 2️⃣ **Reportes Excel/PDF** (api/reports/)

- `excel_generator.py`: Genera archivos XLSX con gráficos
- `pdf_generator.py`: Genera PDFs con resumen
- Guardados en `media/reports/`

### 3️⃣ **JSON Exports** (Auditoría)

- `media/reports/dga/dga_hourly_20260120_15.json`
- Backup de cada envío a DGA

---

## 🎨 Django Admin (Interfaces de Gestión)

### **admin.py** - Admin Principal
- Registro de `CatchmentPoint` (ya en core/admin.py)
- Registro de `TelemetryRecord` (ya en core/admin.py)
- Inline `ComplianceConfigInline`

### **admin_configuration.py** - Configuraciones
- `ConfigurationSchemeAdmin`: Esquemas reutilizables
- `ConfigurationSchemeFieldAdmin`: Campos individuales (d1, d2, pulses_factor)
- `PointConfigurationValueAdmin`: Valores por punto

### **admin_compliance.py** - Compliance ⭐ NUEVO
- `ComplianceProviderAdmin`: Gestión de DGA, SMA, etc.
- `PointComplianceConfigAdmin`: Configurar qué punto envía a qué proveedor
- Estadísticas visuales: tasa de éxito, total envíos, errores

### **providers/admin.py** - Proveedores de Datos
- `TelemetryProviderAdmin`: Configurar Twin, Novus, MQTT
- `CatchmentPointProviderAdmin`: Asociar punto con proveedor
- Test de conectividad integrado

### **providers/admin_mqtt.py** - Configuración MQTT
- `MQTTBrokerAdmin`: Configurar broker (host, port, credenciales)
- `MQTTTopicAdmin`: Configurar tópicos de suscripción
- `MQTTMappingFieldAdmin`: Mapear campos JSON a variables

---

## 🔑 Conceptos Clave

### 📊 **Sistema V3 Dinámico vs Legacy**

| Aspecto | Legacy (V1/V2) | V3 Dinámico |
|---------|----------------|-------------|
| **Variables** | Hardcodeadas en código | `CoreVariable` en BD |
| **Fórmulas** | flow.py, nivel.py, total.py | `FormulaEngine` con sintaxis {var} |
| **Configuración** | ProfileDataConfig (estático) | PointConfigurationValue + Scheme |
| **Proveedores** | Campos booleanos (is_tdata, is_novus) | TelemetryProvider + ProviderManager |
| **Storage** | Columnas separadas (flow, nivel, total) | JSON dinámico: data = {"flow": 12.5} |
| **Compliance** | send_dga hardcodeado | ComplianceProvider dinámico |

### 🔄 **¿Cómo agregar un nuevo proveedor?**

**Antes (Legacy):**
```python
# Modificar modelos
CatchmentPoint.add_field('is_nuevo_proveedor', BooleanField)

# Crear cronjob específico
nuevo_proveedor_cronjob.py

# Modificar save_telemetry_data()
if point.is_nuevo_proveedor:
    # lógica específica
```

**Ahora (V3 Dinámico):**
```python
# Solo Django Admin:
TelemetryProvider.objects.create(
    name='nuevo_proveedor',
    provider_type='api',
    base_url='https://api.nuevo.com',
    auth_method='bearer',
    # ...
)

# Asociar a punto:
CatchmentPointProvider.objects.create(
    point=punto,
    provider=nuevo_proveedor,
    device_id='sensor_123'
)

# ¡Listo! ProviderManager lo detecta automáticamente
```

### 🧩 **¿Cómo agregar una nueva variable?**

**Antes (Legacy):**
```python
# Modificar TelemetryRecord
class TelemetryRecord(models.Model):
    nueva_variable = DecimalField()  # Nueva columna

# Migración de BD
python manage.py makemigrations
python manage.py migrate

# Modificar cronjobs
# Modificar serializers
# Modificar vistas
```

**Ahora (V3 Dinámico):**
```python
# Django Admin → CoreVariable → Add:
CoreVariable.objects.create(
    point=punto,
    internal_code='nueva_variable',
    type_variable='custom_001',
    operation='FORMULA',
    formula='{var1} * 2 + {config.factor}',
    sources=['var1'],
    is_active=True
)

# ¡Listo! FormulaEngine la evalúa automáticamente
# Se guarda en TelemetryRecord.data JSON
```

---

## 🚀 Tareas Celery (Procesamiento Asíncrono)

### **api/celery_app.py** - Scheduler

**Tareas de Telemetría:**
```python
'collect-telemetry-1min': cada 60 segundos
'collect-telemetry-5min': cada 5 minutos
'collect-telemetry-10min': cada 10 minutos
'collect-telemetry-60min': cada hora
```

**Tareas de Compliance:**
```python
'process-compliance-queue': cada 3 minutos
  → Envía datos a DGA, SMA, etc.
  → Reintenta envíos fallidos
  → Guarda logs de auditoría
```

**Tareas de Reportes:**
```python
'daily-bulletin': 01:00 AM
'dga-major-hourly': cada hora a las :05
```

---

## 📝 Archivos de Documentación

| Archivo | Descripción |
|---------|-------------|
| [ANALISIS_OPERACIONES.md](api/telemetry/ANALISIS_OPERACIONES.md:1-724) | Análisis técnico completo (724 líneas) |
| [IMPLEMENTACION_COMPLETA.md](api/telemetry/IMPLEMENTACION_COMPLETA.md:1-500) | Estado de implementación V3 |
| [MIGRATION_STATUS.md](api/telemetry/MIGRATION_STATUS.md:1-300) | Status de migraciones |
| [VALIDACION_COMPLETA.md](api/telemetry/VALIDACION_COMPLETA.md:1-400) | Validación de datos |
| [MIGRACION_COMPLIANCE_COMPLETA.md](MIGRACION_COMPLIANCE_COMPLETA.md:1-600) | Migración DGA → Compliance dinámico |
| [FLUJO_DJANGO_ADMIN_COMPLIANCE.md](FLUJO_DJANGO_ADMIN_COMPLIANCE.md:1-500) | Workflow de configuración |
| [ANALISIS_ARQUITECTURA_MQTT_DGA.md](ANALISIS_ARQUITECTURA_MQTT_DGA.md:1-600) | Análisis de duplicación MQTT |

---

## 🎓 Glosario

| Término | Significado |
|---------|-------------|
| **CatchmentPoint** | Punto físico de monitoreo (pozo, río, canal) |
| **TelemetryRecord** | Snapshot de datos en un momento específico |
| **CoreVariable** | Definición de qué medir en un punto |
| **Provider** | Fuente de datos (Twin, Novus, MQTT) |
| **Handler** | Conector que obtiene datos del provider |
| **FormulaEngine** | Motor que evalúa fórmulas dinámicas |
| **Compliance** | Envío regulatorio (DGA, SMA, INDH) |
| **Unified Processing** | Lógica central de guardado |
| **Legacy** | Sistema antiguo (V1/V2) en proceso de deprecación |
| **Dynamic V3** | Sistema actual flexible y extensible |

---

## 💡 Preguntas Frecuentes

### ❓ ¿Por qué hay tantos archivos de modelos?

Separación de responsabilidades:
- `catchment_points.py`: Dominio de puntos físicos
- `telemetry.py`: Dominio de registros y variables
- `configuration.py`: Dominio de configuraciones
- `providers/`: Dominio de proveedores externos

### ❓ ¿Por qué TelemetryRecord tiene data JSON y no columnas?

**Flexibilidad:**
- Cada punto puede tener variables diferentes
- No necesitas migraciones para agregar variables
- Escalable a millones de registros sin columnas vacías
- Django tiene índices GIN para búsquedas eficientes en JSON

### ❓ ¿Qué es ProviderManager?

**Enrutador inteligente:**
- Desacopla el código de los proveedores específicos
- Permite cambiar de Twin a Novus sin modificar código
- Soporta fallback automático si un proveedor falla
- Cachea configuraciones para mejor rendimiento

### ❓ ¿Qué es FormulaEngine?

**Calculadora dinámica:**
- Evalúa fórmulas tipo Excel: `{var1} * 2 + {config.factor}`
- Reemplaza funciones hardcodeadas (flow.py, nivel.py)
- Permite a usuarios crear variables sin programar
- Soporta variables previas y tiempo transcurrido

### ❓ ¿Qué es Compliance?

**Envío regulatorio:**
- DGA obliga reportar caudales cada hora
- SMA obliga reportar descargas industriales
- ComplianceProvider abstrae estos envíos
- Sistema dinámico permite agregar nuevos organismos

### ❓ ¿Por qué hay código legacy?

**Migración gradual:**
- Sistema antiguo (V1/V2) funcionaba con columnas estáticas
- Sistema nuevo (V3) es dinámico con JSON
- Mantener compatibilidad durante transición
- `send_dga` legacy → `ComplianceProvider` dinámico

---

## 🎯 Conclusión

### ✅ Fortalezas del Sistema

1. **Flexible**: Agregar proveedores/variables sin código
2. **Escalable**: JSON data field crece con necesidades
3. **Desacoplado**: Providers abstrae fuentes de datos
4. **Dinámico**: FormulaEngine para cálculos complejos
5. **Robusto**: Validaciones, reintentos, logs de auditoría
6. **Moderno**: Celery, MQTT, REST APIs, Django Admin rico

### ⚠️ Áreas de Complejidad

1. **Curva de aprendizaje**: Muchos conceptos (Providers, Handlers, Engine)
2. **Migración legacy**: Código antiguo coexiste con nuevo
3. **Documentación**: Dispersa en múltiples archivos MD
4. **Testing**: Falta cobertura completa de tests unitarios

### 🚀 Recomendaciones

1. **Deprecar Legacy Completo**:
   - Eliminar `send_dga` de TelemetryRecord
   - Migrar todos los puntos a ComplianceProvider
   - Eliminar campos `is_tdata`, `is_novus` de CatchmentPoint

2. **Unificar Documentación**:
   - Un solo archivo maestro con índice
   - Diagramas visuales (Mermaid, PlantUML)
   - Ejemplos prácticos por caso de uso

3. **Testing**:
   - Cobertura de FormulaEngine (unit tests)
   - Integración de ProviderManager con mocks
   - E2E tests: MQTT → save_telemetry_data → Compliance

4. **Monitoreo**:
   - Dashboard Grafana con métricas de Prometheus
   - Alertas en Google Chat para fallos de provider
   - Logs estructurados con Elasticsearch

---

**Autor:** Claude (Anthropic)
**Fecha:** 2026-01-20
**Versión:** 3.0.0
