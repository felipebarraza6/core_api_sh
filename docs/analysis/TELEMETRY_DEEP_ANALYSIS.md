# Análisis Profundo: Módulo de Telemetría SmartHydro

**Fecha:** 2026-01-21  
**Versión:** Análisis v1.0  
**Alcance:** Preparación, definición y comportamiento del sistema de telemetría

---

## 1. Visión General del Sistema

El módulo de Telemetría es el corazón operativo de SmartHydro. Gestiona el ciclo completo de datos desde sensores remotos hasta su almacenamiento, procesamiento y reporte a entidades regulatorias.

### Flujo Principal

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           FLUJO DE TELEMETRÍA                                         │
│                                                                                       │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│  │   SENSOR    │────▶│  PROVEEDOR  │────▶│  INGESTION  │────▶│  REGISTRO   │          │
│  │  (Campo)    │     │ (TData/TTN) │     │  (Parser)   │     │ (TelemetryRecord)     │
│  └─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘          │
│                                                                      │                │
│                                                                      ▼                │
│                                                              ┌─────────────┐          │
│                                                              │ COMPLIANCE  │          │
│                                                              │ (DGA/SMA)   │          │
│                                                              └─────────────┘          │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Arquitectura de Modelos

### 2.1 Jerarquía del Punto de Captación

```
                    ┌─────────────────────────────────────────┐
                    │           CatchmentPoint                │
                    │         (Punto de Captación)            │
                    │                                         │
                    │  • technical_survey (FK → CRM)          │
                    │  • owner_user (FK → User)               │
                    │  • processing_scheme (FK → Scheme)      │
                    │  • configuration_scheme (FK → Config)   │
                    │  • frequency (FK → SamplingFrequency)   │
                    │  • documents (M2M → Document)           │
                    └────────────────────┬────────────────────┘
                                         │
           ┌─────────────────────────────┼─────────────────────────────┐
           │                             │                             │
           ▼                             ▼                             ▼
    ┌──────────────┐             ┌──────────────┐             ┌──────────────┐
    │ProfileIkolu  │             │ProfileData   │             │CoreVariable  │
    │(Módulos)     │             │Config        │             │(Variables)   │
    │              │             │              │             │              │
    │ • m1: Pozo   │             │ • d1: Prof.  │             │ • TOTALIZADO │
    │ • m2: DGA    │             │ • d2: Bomba  │             │ • NIVEL      │
    │ • m3: Report │             │ • d3: Nivel  │             │ • CAUDAL     │
    │ • m4: Graphs │             │ • token      │             │ • GENÉRICO   │
    │ • m5: Indic. │             │ • extra_conf │             │              │
    │ • m6: Alarm  │             │ • addition   │             │              │
    │ • m7: Docs   │             │              │             │              │
    └──────────────┘             └──────────────┘             └──────────────┘
                                         │
                                         ▼
                                 ┌──────────────┐
                                 │TelemetryRecord│
                                 │ (Datos)       │
                                 │               │
                                 │ • timestamp   │
                                 │ • data (JSON) │
                                 │ • compliance  │
                                 └───────────────┘
```

---

### 2.2 Modelos Principales

| Modelo | Propósito | Relación Clave |
|:-------|:----------|:---------------|
| **CatchmentPoint** | Punto físico de medición (pozo, caudalímetro) | Raíz de todo el sistema |
| **ProfileIkoluCatchment** | Módulos habilitados para el punto | 1:1 con CatchmentPoint |
| **ProfileDataConfigCatchment** | Configuración técnica del sensor | 1:1 con CatchmentPoint |
| **CoreVariable** | Variables medibles del punto | N:1 con CatchmentPoint |
| **TelemetryRecord** | Registro de datos recibidos | N:1 con CatchmentPoint |
| **TelemetryScheme** | Plantilla reutilizable de procesamiento | N:N con CatchmentPoints |
| **ConfigurationScheme** | Plantilla de configuración estática | N:N con CatchmentPoints |

---

## 3. Sistema de Esquemas (Plantillas)

El sistema utiliza dos tipos de esquemas para estandarizar configuraciones:

### 3.1 TelemetryScheme (Procesamiento Dinámico)

Define **cómo procesar** los datos recibidos.

```
┌─────────────────────────────────────────────────────────────┐
│                    TelemetryScheme                           │
│                   "Pozo Subterráneo DGA"                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ SchemeVariable  │  │ SchemeVariable  │  │SchemeVariable│ │
│  │ TOTALIZADO      │  │ NIVEL           │  │ CAUDAL       │ │
│  │                 │  │                 │  │              │ │
│  │ operation:      │  │ operation:      │  │ operation:   │ │
│  │ FORMULA         │  │ FORMULA         │  │ DIFF         │ │
│  │                 │  │                 │  │              │ │
│  │ formula:        │  │ formula:        │  │ sources:     │ │
│  │ {pulses}/       │  │ {config.d3} -   │  │ [total_prev, │ │
│  │ {config.factor} │  │ {nivel_raw}     │  │  total_now]  │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 ConfigurationScheme (Datos Estáticos)

Define **qué parámetros** se necesitan configurar.

```
┌─────────────────────────────────────────────────────────────┐
│                  ConfigurationScheme                         │
│                  "Pozo Estándar v2"                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ConfigurationSchemeField                                 ││
│  ├─────────────────────────────────────────────────────────┤│
│  │ code: "d1"          | name: "Profundidad"     | decimal ││
│  │ code: "d2"          | name: "Posición Bomba"  | decimal ││
│  │ code: "d3"          | name: "Posición Nivel"  | decimal ││
│  │ code: "d4"          | name: "Diámetro Salida" | decimal ││
│  │ code: "pulses_factor"| name: "Factor Pulsos" | decimal ││
│  │ code: "addition"    | name: "Offset Reset"    | integer ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Pipeline de Ingestion de Datos

### 4.1 Fuentes de Datos

| Proveedor | Protocolo | Modelo |
|:----------|:----------|:-------|
| TData | REST API | `TelemetryProvider` |
| The Things Network | MQTT | `MQTTProviderConfig` |
| Tago.io | REST API | `TelemetryProvider` |
| Manual | Formulario | `ManualComplianceRecord` |

### 4.2 Flujo de Procesamiento

```
1. RECEPCIÓN
   └─▶ Webhook / MQTT / API Poll
       └─▶ Raw JSON {sensor_id: value, ...}

2. PARSING
   └─▶ PayloadParsingRule (MQTT) / Handler (API)
       └─▶ Identificar punto y variables
       └─▶ Extraer valores crudos

3. TRANSFORMACIÓN
   └─▶ CoreVariable.formula
       └─▶ Aplicar scale_factor, offset
       └─▶ Calcular variables virtuales
       └─▶ Validar min_value, max_value

4. ALMACENAMIENTO
   └─▶ TelemetryRecord
       └─▶ data: {"TOTALIZADO": 1234.5, "NIVEL": 45.2, ...}
       └─▶ metadata: {provider: "tdata", raw: {...}}

5. COMPLIANCE
   └─▶ PointComplianceConfig
       └─▶ Enviar a DGA/SMA si corresponde
       └─▶ Actualizar compliance_status en TelemetryRecord
```

---

## 5. Sistema de Variables

### 5.1 Tipos de Variables (VariableType)

| Código | Descripción | Fórmula Típica |
|:-------|:------------|:---------------|
| `TOTALIZADO` | Acumulador de pulsos | `{pulses} / {config.pulses_factor} + {config.addition}` |
| `NIVEL` | Nivel freático | `{config.d3} - {nivel_raw}` |
| `CAUDAL` | Caudal instantáneo | `({total} - {prev.total}) / {time.diff_seconds} * 1000` |
| `CAUDAL_PROMEDIO` | Promedio de caudal | `AVG({caudal})` sobre período |
| `GENERIC` | Dato directo | `{raw_value} * {scale_factor} + {offset}` |

### 5.2 Operaciones Disponibles

| Operación | Descripción | Uso |
|:----------|:------------|:----|
| `PHYSICAL` | Dato directo del sensor | Variables primarias |
| `SUM` | Suma de variables | Totales combinados |
| `DIFF` | Diferencia A - B | Consumo entre lecturas |
| `MUL` | Multiplicación | Factores de conversión |
| `AVG` | Promedio | Promedios horarios/diarios |
| `FORMULA` | Fórmula personalizada | Cálculos complejos |

### 5.3 Sintaxis de Fórmulas

```python
# Variables del punto
{var_code}              # Valor actual de otra variable
{prev.var_code}         # Valor anterior de una variable

# Configuración del punto (ConfigurationScheme)
{config.d3}             # Valor de campo de configuración
{config.pulses_factor}  # Factor de pulsos

# Sistema
{system.key}            # Valor de SystemConfiguration
{time.diff_seconds}     # Diferencia de tiempo en segundos

# Ejemplo completo
({pulses} * {config.pulses_factor}) / 1000 + {config.addition}
```

---

## 6. Sistema de Compliance

### 6.1 Arquitectura Dinámica

```
┌─────────────────────────────────────────────────────────────┐
│                   ComplianceProvider                         │
│                      (DGA, SMA, etc.)                        │
├─────────────────────────────────────────────────────────────┤
│  • base_url                                                  │
│  • auth_method (BASIC, TOKEN, CERTIFICATE)                   │
│  • credential_template                                       │
│  • request_template                                          │
│  • compliance_standard (FK → ComplianceStandard)             │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          │ 1:N
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  PointComplianceConfig                       │
│             (Configuración por Punto)                        │
├─────────────────────────────────────────────────────────────┤
│  • point (FK → CatchmentPoint)                               │
│  • provider (FK → ComplianceProvider)                        │
│  • is_enabled                                                │
│  • credential_override (JSON)                                │
│  • submission_frequency (REALTIME, HOURLY, 15MIN)            │
│  • last_successful_submission                                │
│  • error_count                                               │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Estándares de Cumplimiento

| Estándar | Frecuencia | Descripción |
|:---------|:-----------|:------------|
| DGA | 15 minutos | Dirección General de Aguas |
| SMA | Variable | Superintendencia de Medio Ambiente |
| INDH | Mensual | Instituto Nacional de Derechos Humanos |

---

## 7. Coherencia y Observaciones

### 7.1 ✅ Aspectos Coherentes

| Aspecto | Estado | Comentario |
|:--------|:-------|:-----------|
| Esquemas reutilizables | ✅ | TelemetryScheme y ConfigurationScheme |
| Variables dinámicas | ✅ | CoreVariable con fórmulas flexibles |
| Proveedores múltiples | ✅ | TelemetryProvider + MQTT |
| Compliance dinámico | ✅ | ComplianceProvider con estándares |
| Datos históricos | ✅ | TelemetryRecord con JSON flexible |
| Frecuencias configurables | ✅ | SamplingFrequency dinámico |

### 7.2 ⚠️ Observaciones y Mejoras Sugeridas

#### 7.2.1 Duplicación de Configuración

**Problema:** Hay dos lugares para configurar valores del punto:
1. `ProfileDataConfigCatchment.extra_config` (JSON)
2. `PointConfigurationValue` (modelo relacional)

**Recomendación:** Migrar gradualmente `extra_config` a `PointConfigurationValue` para mejor validación y queryabilidad.

---

#### 7.2.2 Variables Hardcodeadas vs Dinámicas

**Problema:** `SchemeVariable.VARIABLE_TYPES` está hardcodeado pero existe `VariableType` dinámico.

```python
# Hardcodeado en SchemeVariable
VARIABLE_TYPES = [
    ("TOTALIZADO", "Totalizado (Pulsos)"),
    ("NIVEL", "Nivel Freático"),
    ...
]

# Dinámico en VariableType
class VariableType(ModelApi):
    code = models.CharField(...)
    name = models.CharField(...)
```

**Recomendación:** Usar `VariableType` como fuente única de verdad.

---

#### 7.2.3 Perfil Ikolu Rígido

**Problema:** `ProfileIkoluCatchment` tiene módulos hardcodeados (m1, m2, ... m7).

**Recomendación:** Considerar un modelo `ModuleSubscription` dinámico:

```python
class ModuleSubscription(ModelApi):
    point = FK(CatchmentPoint)
    module = FK(AvailableModule)  # Catálogo de módulos
    start_date = DateField
    subscription_type = CharField  # MENSUAL, ANUAL, etc.
    is_active = BooleanField
```

---

#### 7.2.4 Legacy Fields Pendientes

| Campo | Modelo | Estado |
|:------|:-------|:-------|
| `frecuency` (char) | CatchmentPoint | [DEP] Usar `frequency` (FK) |
| `project` (FK) | CatchmentPoint | [DEP] Usar `technical_survey.project` |

---

### 7.3 ❌ Problemas Potenciales

#### 7.3.1 Circular Import Risk

La relación `CatchmentPoint` ↔ `TechnicalSurvey` cruza apps (telemetry ↔ crm).
Usar strings para ForeignKey (`"crm.TechnicalSurvey"`) resuelve imports pero dificulta validaciones en código.

#### 7.3.2 Falta de Índices en TelemetryRecord.data

El campo `data` (JSONField) tiene GinIndex, pero queries complejas como:
```python
TelemetryRecord.objects.filter(data__TOTALIZADO__gte=1000)
```
Pueden ser lentas sin índices específicos.

**Recomendación:** Crear índices parciales o funcionales para campos JSON frecuentes.

---

## 8. Diagrama Completo de Relaciones

```
                                  ┌──────────────┐
                                  │    Client    │
                                  └──────┬───────┘
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │   Project    │
                                  └──────┬───────┘
                                         │
                                         ▼
                               ┌──────────────────┐
                               │ TechnicalSurvey  │
                               │   (CRM)          │
                               └────────┬─────────┘
                                        │ 1:1
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                                 CatchmentPoint                                        │
│                              (Punto de Captación)                                     │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │
│  │ProfileIkolu │  │ProfileData  │  │Telemetry    │  │Configuration│                   │
│  │(Módulos)    │  │Config       │  │Scheme       │  │Scheme       │                   │
│  │  1:1        │  │(Técnico)    │  │(Proceso)    │  │(Estático)   │                   │
│  │             │  │  1:1        │  │  FK         │  │  FK         │                   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘                   │
│                                                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │
│  │CoreVariable │  │Telemetry    │  │Point        │  │Point        │                   │
│  │(Variables)  │  │Record       │  │Compliance   │  │Provider     │                   │
│  │  1:N        │  │(Datos)      │  │Config       │  │(Telemetría) │                   │
│  │             │  │  1:N        │  │  1:N        │  │  1:N        │                   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘                   │
│                                                                                       │
│  ┌─────────────┐  ┌─────────────┐                                                     │
│  │Documents    │  │DataPoint    │                                                     │
│  │(Archivos)   │  │(Granular)   │                                                     │
│  │  M2M        │  │  1:N        │                                                     │
│  └─────────────┘  └─────────────┘                                                     │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
            ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
            │Telemetry    │     │Compliance   │     │MQTT         │
            │Provider     │     │Provider     │     │Provider     │
            │(API)        │     │(DGA/SMA)    │     │(TTN)        │
            └─────────────┘     └─────────────┘     └─────────────┘
```

---

## 9. Próximos Pasos

1. **Migración de Legacy:**
   - Eliminar `frecuency` (char) cuando todos los puntos usen `frequency` (FK)
   - Eliminar `project` cuando todos usen `technical_survey.project`

2. **Unificación de Variables:**
   - Migrar `SchemeVariable.type_variable` a usar `VariableType` FK

3. **Dinamización de Módulos:**
   - Evaluar migración de `ProfileIkoluCatchment` a modelo dinámico

4. **Optimización de Índices:**
   - Agregar índices funcionales para campos JSON frecuentes

5. **Tests de Integración:**
   - Crear tests para pipeline completo de ingestion
   - Validar compliance submissions
