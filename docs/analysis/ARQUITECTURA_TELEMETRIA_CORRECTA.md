# 🚀 Arquitectura de Telemetría - Sistema 100% Dinámico

**Fecha:** 2026-01-20
**Visión:** Sistema completamente configurable sin código hardcodeado

---

## 🎯 CONCEPTO CLAVE: TODO ES CONFIGURABLE

> **Principio fundamental:** NO existen módulos hardcodeados de "caudal", "nivel" o "totalizado".
> **TODO** el procesamiento se define mediante **variables** + **FormulaEngine**.
> Este enfoque permite que el **mismo método se propague a TODOS los contextos** (ingesta, procesamiento, compliance, reportes).

---

## 🏗️ Arquitectura Real del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                  INGESTA (Múltiples Fuentes)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Twin API     │  │ Novus API    │  │ Nettra API   │         │
│  │ (Proveedor)  │  │ (Proveedor)  │  │ (Proveedor)  │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                  │
│         └──────────────────┴──────────────────┘                  │
│                            │                                      │
│         ┌──────────────────▼──────────────────┐                 │
│         │   NUESTRO MQTT BROKER               │                 │
│         │   (Puede recibir de CUALQUIER       │                 │
│         │    equipo, sea su proveedor Twin,   │                 │
│         │    Novus, o el que sea)             │                 │
│         └──────────────────┬──────────────────┘                 │
│                            │                                      │
└────────────────────────────┼──────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────┐
│                    PROVIDER LAYER                                 │
│  (Parseo de datos del proveedor + Códigos de error)              │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Cada proveedor tiene su:                                        │
│  ├─ Parser de payload                                            │
│  ├─ Mapeo de códigos de error                                    │
│  ├─ Normalización de datos                                       │
│  └─ Extracción de metadata del equipo                            │
│                                                                   │
│  Salida estandarizada:                                           │
│  {                                                                │
│    "raw_data": {...},           # Datos crudos del proveedor     │
│    "device_metadata": {...},    # Info del equipo                │
│    "errors": [...],             # Códigos de error parseados     │
│    "timestamp": "..."           # Timestamp del equipo           │
│  }                                                                │
│                                                                   │
└────────────────────────────┬──────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────┐
│              VARIABLE PROCESSING ENGINE                           │
│         (TODO basado en CoreVariable + FormulaEngine)             │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Para CADA variable definida en CoreVariable:                    │
│                                                                   │
│  1. EXTRACCIÓN (según provider_key)                              │
│     └─ Obtener valor crudo del raw_data                          │
│                                                                   │
│  2. TRANSFORMACIÓN (según operation + formula)                   │
│     ├─ PHYSICAL: value * scale_factor + offset                  │
│     ├─ FORMULA:  FormulaEngine.evaluate(formula, context)        │
│     ├─ SUM:      Σ(source_variables)                             │
│     ├─ DIFF:     source_var1 - source_var2                       │
│     ├─ AVG:      Promedio de source_variables                    │
│     └─ MUL:      Π(source_variables)                             │
│                                                                   │
│  3. VALIDACIÓN (según min_value, max_value)                      │
│     └─ Verificar que value esté en rango válido                  │
│                                                                   │
│  4. CONSTRUCCIÓN DE CONTEXTO                                     │
│     └─ Todas las variables procesadas están disponibles          │
│        para fórmulas de variables dependientes                   │
│                                                                   │
└────────────────────────────┬──────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────┐
│                    STORAGE (TelemetryRecord)                      │
│                     JSONField 100% Dinámico                       │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  {                                                                │
│    "data": {                    # Variables procesadas            │
│      "var_1": 12.5,                                              │
│      "var_2": 3.2,                                               │
│      "calculated_var": 45.0,                                     │
│      ...                        # CUALQUIER variable definida    │
│    },                                                             │
│    "metadata": {                # Info del equipo/proveedor      │
│      "provider": "twin",                                         │
│      "device_id": "sensor_123",                                  │
│      "firmware": "v2.1.0",                                       │
│      "battery": 85,                                              │
│      "signal": -65                                               │
│    },                                                             │
│    "errors": [                  # Errores parseados              │
│      {"code": "E001", "description": "Sensor desconectado"}     │
│    ]                                                              │
│  }                                                                │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## 🔑 CONCEPTO FUNDAMENTAL: MQTT COMO HUB UNIVERSAL

### ❌ Concepto INCORRECTO:
```
Equipo Twin → Solo puede usar Twin API
Equipo Novus → Solo puede usar Novus API
```

### ✅ Concepto CORRECTO:
```
Equipo Twin → Puede enviar a:
              ├─ Twin API (su proveedor original)
              └─ NUESTRO MQTT BROKER (configurado por nosotros)

Equipo Novus → Puede enviar a:
               ├─ Novus API (su proveedor original)
               └─ NUESTRO MQTT BROKER (configurado por nosotros)

Equipo Custom → SOLO envía a:
                └─ NUESTRO MQTT BROKER
```

### 🎯 Ventaja Competitiva

```
┌────────────────────────────────────────────────────────────┐
│  ESCENARIO: Cliente tiene equipos Twin                     │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Opción 1: Usar Twin API                                  │
│  └─ Dependemos de disponibilidad de Twin                   │
│  └─ Pagamos por API calls a Twin                          │
│  └─ Latencia mayor (Twin → Nosotros)                      │
│                                                             │
│  Opción 2: Configurar equipos → Nuestro MQTT              │
│  └─ Independientes de Twin                                 │
│  └─ Sin costos de API externa                             │
│  └─ Latencia mínima (Equipo → MQTT directo)              │
│  └─ MISMO PROCESAMIENTO (FormulaEngine no cambia)         │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

## 📦 PROVIDER LAYER (Capa de Proveedores)

### Responsabilidades del Provider

```python
class Provider:
    """
    Responsabilidades:
    1. Parsear payload del equipo
    2. Extraer códigos de error específicos del fabricante
    3. Normalizar datos a formato estándar
    4. Extraer metadata del dispositivo
    """

    def parse_payload(self, raw_payload) -> dict:
        """
        Entrada: Payload crudo del equipo/API
        Salida: Datos normalizados

        Ejemplo Twin:
        {
            "raw_data": {
                "5000": 1500,      # Código Twin para "total"
                "5001": 12.5,      # Código Twin para "caudal"
                "5002": 3.2        # Código Twin para "nivel"
            },
            "device_metadata": {
                "device_id": "TWN-123",
                "battery": 85,
                "signal": -65,
                "firmware": "v2.1.0"
            },
            "errors": [
                {
                    "code": "E001",           # Código del fabricante
                    "description": "Sensor nivel desconectado",
                    "severity": "critical"
                }
            ],
            "timestamp": "2026-01-20T10:30:00Z"
        }
        """
```

### ¿Por qué los errores van en el Provider?

```
┌─────────────────────────────────────────────────────────────┐
│  RAZÓN: Cada fabricante tiene sus propios códigos           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Twin:                                                       │
│  └─ Error E001 = "Sensor desconectado"                     │
│  └─ Error E002 = "Batería baja"                            │
│                                                              │
│  Novus:                                                      │
│  └─ Error 0x10 = "Sensor desconectado"                     │
│  └─ Error 0x20 = "Batería baja"                            │
│                                                              │
│  Nettra:                                                     │
│  └─ Error "SENSOR_FAIL" = "Sensor desconectado"            │
│  └─ Error "LOW_BATT" = "Batería baja"                      │
│                                                              │
│  ⚠️ Si intentamos procesar errores de forma genérica,       │
│     perdemos información crítica específica del equipo      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧮 FORMULA ENGINE: EL CORAZÓN DEL SISTEMA

### ❌ ELIMINAR: Módulos Hardcodeados

```python
# ❌ ESTO NO DEBE EXISTIR
def process_caudal_variable(value):
    return value * factor + offset

def process_nivel_variable(value):
    return d1 - value

def process_totalizado_variable(pulses):
    return pulses * factor / 1000
```

### ✅ USAR: FormulaEngine Universal

```python
# ✅ TODO se define en CoreVariable

# Variable 1: Caudal
CoreVariable.objects.create(
    internal_code="caudal_ls",
    operation="FORMULA",
    formula="{raw_caudal} * {scale_factor} + {offset}",
    sources=["raw_caudal"],
    context={
        "scale_factor": 1.0,
        "offset": 0.0
    }
)

# Variable 2: Nivel Freático
CoreVariable.objects.create(
    internal_code="nivel_freatico",
    operation="FORMULA",
    formula="{profundidad_pozo} - {nivel_medido}",
    sources=["nivel_medido"],
    context={
        "profundidad_pozo": 50.0  # Configurable por punto
    }
)

# Variable 3: Volumen desde Pulsos
CoreVariable.objects.create(
    internal_code="volumen_m3",
    operation="FORMULA",
    formula="({pulsos} * {factor_pulso}) / 1000",
    sources=["pulsos"],
    context={
        "factor_pulso": 0.5  # Configurable por equipo
    }
)

# Variable 4: Consumo Diario (dependiente)
CoreVariable.objects.create(
    internal_code="consumo_diario",
    operation="FORMULA",
    formula="{volumen_m3} - {volumen_m3_ayer}",
    sources=["volumen_m3", "volumen_m3_ayer"],
    priority=2  # Se calcula DESPUÉS de volumen_m3
)
```

---

## 🔄 FLUJO COMPLETO DE PROCESAMIENTO

### Ejemplo Real: Equipo Twin enviando a Nuestro MQTT

```
┌────────────────────────────────────────────────────────────┐
│  PASO 1: INGESTA                                           │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Equipo Twin (configurado para enviar a nuestro MQTT)     │
│  └─ Publica en topic: smarthydro/pozo_123/data            │
│                                                             │
│  Payload recibido:                                         │
│  {                                                          │
│    "device_id": "TWN-123",                                 │
│    "timestamp": "2026-01-20T10:30:00Z",                    │
│    "5000": 1500,        # Código Twin = pulsos totales    │
│    "5001": 12.5,        # Código Twin = caudal            │
│    "5002": 3.2,         # Código Twin = nivel             │
│    "battery": 85,                                          │
│    "signal": -65,                                          │
│    "errors": ["E001"]   # Error del equipo                │
│  }                                                          │
│                                                             │
└────────────────────────────────────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────┐
│  PASO 2: PROVIDER PARSING (Twin Provider)                 │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  TwinProvider.parse_payload(raw_payload)                   │
│                                                             │
│  Salida normalizada:                                       │
│  {                                                          │
│    "raw_data": {                                           │
│      "pulsos": 1500,      # Mapeado de "5000"            │
│      "caudal_crudo": 12.5, # Mapeado de "5001"           │
│      "nivel_crudo": 3.2    # Mapeado de "5002"           │
│    },                                                       │
│    "device_metadata": {                                    │
│      "provider": "twin",                                   │
│      "device_id": "TWN-123",                              │
│      "battery": 85,                                        │
│      "signal": -65                                         │
│    },                                                       │
│    "errors": [                                             │
│      {                                                      │
│        "code": "E001",                                     │
│        "description": "Sensor de nivel desconectado",     │
│        "severity": "critical"                              │
│      }                                                      │
│    ],                                                       │
│    "timestamp": "2026-01-20T10:30:00Z"                     │
│  }                                                          │
│                                                             │
└────────────────────────────────────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────┐
│  PASO 3: VARIABLE PROCESSING (FormulaEngine)              │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Variables definidas para este punto:                      │
│                                                             │
│  1. volumen_m3 (priority=1)                               │
│     └─ formula: "({pulsos} * 0.5) / 1000"                 │
│     └─ context: {"pulsos": 1500}                          │
│     └─ resultado: 0.75 m³                                 │
│                                                             │
│  2. caudal_ls (priority=1)                                │
│     └─ formula: "{caudal_crudo} * 1.0 + 0.0"             │
│     └─ context: {"caudal_crudo": 12.5}                    │
│     └─ resultado: 12.5 L/s                                │
│                                                             │
│  3. nivel_freatico (priority=1)                           │
│     └─ formula: "50.0 - {nivel_crudo}"                    │
│     └─ context: {"nivel_crudo": 3.2}                      │
│     └─ resultado: 46.8 m                                  │
│                                                             │
│  4. consumo_hora (priority=2) [DEPENDIENTE]               │
│     └─ formula: "{volumen_m3} - {volumen_m3_hora_anterior}"│
│     └─ context: {                                          │
│          "volumen_m3": 0.75,                              │
│          "volumen_m3_hora_anterior": 0.72                 │
│        }                                                    │
│     └─ resultado: 0.03 m³                                 │
│                                                             │
└────────────────────────────────────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────┐
│  PASO 4: STORAGE                                           │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  TelemetryRecord.objects.create(                           │
│    point_id=123,                                           │
│    timestamp="2026-01-20T10:30:00Z",                       │
│    data={                                                   │
│      "volumen_m3": 0.75,                                   │
│      "caudal_ls": 12.5,                                    │
│      "nivel_freatico": 46.8,                               │
│      "consumo_hora": 0.03                                  │
│    },                                                       │
│    metadata={                                               │
│      "provider": "twin",                                   │
│      "device_id": "TWN-123",                              │
│      "battery": 85,                                        │
│      "signal": -65                                         │
│    },                                                       │
│    errors=[                                                 │
│      {                                                      │
│        "code": "E001",                                     │
│        "description": "Sensor de nivel desconectado",     │
│        "severity": "critical"                              │
│      }                                                      │
│    ],                                                       │
│    is_error=True  # Porque hay error crítico              │
│  )                                                          │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

## 🌟 VENTAJA COMPETITIVA: PROPAGACIÓN DEL MÉTODO

### El Mismo FormulaEngine se Usa en TODOS los Contextos

```
┌─────────────────────────────────────────────────────────────┐
│  CONTEXTO 1: INGESTA                                        │
├─────────────────────────────────────────────────────────────┤
│  FormulaEngine.evaluate(variable.formula, raw_data)         │
│  └─ Procesa datos crudos del equipo                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  CONTEXTO 2: REPORTES                                       │
├─────────────────────────────────────────────────────────────┤
│  FormulaEngine.evaluate(report_formula, aggregated_data)    │
│  └─ Ejemplo: "SUM({volumen_m3}) WHERE month = 1"           │
│  └─ Calcula totales, promedios, agregaciones                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  CONTEXTO 3: COMPLIANCE                                     │
├─────────────────────────────────────────────────────────────┤
│  FormulaEngine.evaluate(compliance_rule, telemetry_data)    │
│  └─ Ejemplo: "IF {caudal_ls} > {max_autorizado} THEN alert"│
│  └─ Valida cumplimiento de normas                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  CONTEXTO 4: ALERTAS                                        │
├─────────────────────────────────────────────────────────────┤
│  FormulaEngine.evaluate(alert_condition, current_data)      │
│  └─ Ejemplo: "{nivel_freatico} < 10 OR {caudal_ls} > 50"  │
│  └─ Dispara alertas basadas en condiciones                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  CONTEXTO 5: ANÁLISIS                                       │
├─────────────────────────────────────────────────────────────┤
│  FormulaEngine.evaluate(analysis_formula, historical_data)  │
│  └─ Ejemplo: "TREND({caudal_ls}, days=30)"                 │
│  └─ Detecta tendencias, patrones, anomalías                 │
└─────────────────────────────────────────────────────────────┘
```

### 🚀 Resultado

```
┌────────────────────────────────────────────────────────────┐
│  UN SOLO MOTOR (FormulaEngine) impulsa TODO el sistema    │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ Consistencia total                                     │
│  ✅ Sin duplicación de lógica                              │
│  ✅ Fácil de mantener (un solo lugar)                      │
│  ✅ Extensible sin límites                                 │
│  ✅ Testing simplificado                                   │
│  ✅ Documentación unificada                                │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

## 🔧 CONFIGURACIÓN DE VARIABLES (CoreVariable)

### Estructura Completa

```python
CoreVariable
├─ point: FK(CatchmentPoint)         # Punto asociado
├─ internal_code: str                 # Identificador único
├─ name: str                          # Nombre legible
├─ unit: str                          # Unidad de medida
│
├─ operation: str                     # Tipo de operación
│   ├─ "PHYSICAL"   → Valor directo del sensor (con scale/offset)
│   ├─ "FORMULA"    → Expresión matemática libre
│   ├─ "SUM"        → Suma de variables fuente
│   ├─ "DIFF"       → Diferencia
│   ├─ "AVG"        → Promedio
│   ├─ "MUL"        → Multiplicación
│   ├─ "MIN"        → Mínimo
│   ├─ "MAX"        → Máximo
│   └─ "CUSTOM"     → Función Python personalizada
│
├─ formula: str                       # Fórmula (si operation=FORMULA)
│   └─ Ejemplo: "({var1} + {var2}) * {factor}"
│
├─ sources: JSONField                 # Variables de origen
│   └─ ["var1", "var2", "var3"]
│
├─ context: JSONField                 # Constantes/configuración
│   └─ {"factor": 1.5, "offset": 2.0, "max": 100}
│
├─ provider_key: str                  # Key en payload del proveedor
│   └─ Ejemplo: "5000" (Twin), "flow" (Novus), "Q" (Nettra)
│
├─ scale_factor: float                # Factor de escala (default: 1.0)
├─ offset: float                      # Offset (default: 0.0)
├─ min_value: float                   # Valor mínimo válido
├─ max_value: float                   # Valor máximo válido
│
├─ priority: int                      # Orden de cálculo
│   └─ Variables con priority menor se calculan primero
│
├─ is_virtual: bool                   # ¿Es calculada o física?
│   ├─ False → Viene directamente del equipo
│   └─ True  → Se calcula a partir de otras variables
│
├─ is_active: bool                    # ¿Está activa?
└─ validation_rule: JSONField         # Reglas de validación
    └─ {"type": "range", "min": 0, "max": 100}
```

---

## 📋 EJEMPLOS DE CONFIGURACIÓN

### Ejemplo 1: Caudal Simple

```python
# Variable física directa del sensor
CoreVariable.objects.create(
    point=punto,
    internal_code="caudal_ls",
    name="Caudal Instantáneo",
    unit="L/s",
    operation="PHYSICAL",
    provider_key="5001",  # Código Twin
    scale_factor=1.0,
    offset=0.0,
    min_value=0.0,
    max_value=50.0,
    priority=1,
    is_virtual=False
)
```

### Ejemplo 2: Volumen desde Pulsos

```python
# Variable calculada con fórmula
CoreVariable.objects.create(
    point=punto,
    internal_code="volumen_m3",
    name="Volumen Acumulado",
    unit="m³",
    operation="FORMULA",
    formula="({pulsos} * {factor_pulso}) / 1000",
    sources=["pulsos"],
    context={
        "factor_pulso": 0.5  # Factor específico del caudalímetro
    },
    min_value=0.0,
    priority=1,
    is_virtual=True
)
```

### Ejemplo 3: Consumo Diario (Dependiente)

```python
# Variable que depende de otra variable
CoreVariable.objects.create(
    point=punto,
    internal_code="consumo_diario",
    name="Consumo Diario",
    unit="m³",
    operation="DIFF",
    sources=["volumen_m3", "volumen_m3_ayer"],
    priority=2,  # Se calcula DESPUÉS de volumen_m3
    is_virtual=True
)
```

### Ejemplo 4: Eficiencia (Multi-variable)

```python
# Variable calculada con múltiples fuentes
CoreVariable.objects.create(
    point=punto,
    internal_code="eficiencia_sistema",
    name="Eficiencia del Sistema",
    unit="%",
    operation="FORMULA",
    formula="({volumen_entregado} / {volumen_captado}) * 100",
    sources=["volumen_entregado", "volumen_captado"],
    min_value=0.0,
    max_value=100.0,
    priority=3,
    is_virtual=True
)
```

### Ejemplo 5: Condición Compleja

```python
# Variable con lógica condicional
CoreVariable.objects.create(
    point=punto,
    internal_code="estado_bomba",
    name="Estado de la Bomba",
    unit="",
    operation="FORMULA",
    formula="""
    IF({caudal_ls} > 0.5, 'OPERANDO',
       IF({caudal_ls} > 0.1, 'ARRANQUE',
          'DETENIDO'))
    """,
    sources=["caudal_ls"],
    priority=2,
    is_virtual=True
)
```

---

## 🎯 ARQUITECTURA DE PROVIDER CORRECTO

### Modelo de Provider

```python
TelemetryProvider
├─ name: str                          # "twin", "novus", "mqtt_custom"
├─ display_name: str                  # "Twin Hidro"
├─ provider_type: str                 # "api" | "mqtt"
│
├─ # Configuración de conexión
├─ base_url: str                      # URL del API (si type=api)
├─ auth_method: str                   # "bearer" | "basic" | "oauth2"
├─ auth_config: JSONField             # Credenciales
│
├─ # Parseo de payload
├─ payload_parser: str                # Nombre de la clase parser
│   └─ "TwinPayloadParser", "NovusPayloadParser", etc.
│
├─ # Mapeo de códigos
├─ variable_mapping: JSONField        # Mapeo de códigos a variables
│   └─ {
│        "5000": "pulsos",
│        "5001": "caudal_crudo",
│        "5002": "nivel_crudo"
│      }
│
├─ error_codes: JSONField             # Diccionario de errores
│   └─ {
│        "E001": {
│          "description": "Sensor desconectado",
│          "severity": "critical",
│          "suggested_action": "Revisar conexión del sensor"
│        },
│        "E002": {...}
│      }
│
└─ metadata_extraction: JSONField     # Reglas para extraer metadata
    └─ {
         "battery": "bat_level",
         "signal": "rssi",
         "firmware": "fw_version"
       }
```

### Parser de Payload

```python
class TwinPayloadParser:
    """Parser específico para equipos Twin"""

    def parse(self, raw_payload: dict, provider_config: dict) -> dict:
        """
        Args:
            raw_payload: Payload crudo del equipo
            provider_config: Configuración del provider

        Returns:
            {
                "raw_data": {...},
                "device_metadata": {...},
                "errors": [...],
                "timestamp": "..."
            }
        """
        # 1. Mapear códigos Twin a variables estándar
        mapped_data = {}
        for twin_code, value in raw_payload.items():
            if twin_code in provider_config['variable_mapping']:
                var_name = provider_config['variable_mapping'][twin_code]
                mapped_data[var_name] = value

        # 2. Extraer metadata del dispositivo
        metadata = {
            "provider": "twin",
            "device_id": raw_payload.get("device_id"),
            "battery": raw_payload.get("battery"),
            "signal": raw_payload.get("signal"),
            "firmware": raw_payload.get("fw_version")
        }

        # 3. Parsear códigos de error específicos de Twin
        errors = []
        if "errors" in raw_payload:
            for error_code in raw_payload["errors"]:
                error_info = provider_config['error_codes'].get(error_code, {})
                errors.append({
                    "code": error_code,
                    "description": error_info.get("description", "Unknown error"),
                    "severity": error_info.get("severity", "warning"),
                    "suggested_action": error_info.get("suggested_action", "")
                })

        # 4. Extraer timestamp
        timestamp = raw_payload.get("timestamp") or datetime.now().isoformat()

        return {
            "raw_data": mapped_data,
            "device_metadata": metadata,
            "errors": errors,
            "timestamp": timestamp
        }
```

---

## 🔄 PROCESO DE INGESTA MQTT PROPIO

### Configuración de Equipo para Nuestro MQTT

```python
# Configurar punto para recibir datos vía MQTT
CatchmentPointMQTT.objects.create(
    point=punto,
    topic="smarthydro/pozo_123/data",
    broker_host="mqtt.smarthydro.app",  # NUESTRO broker
    broker_port=1883,
    qos=1,

    # Parser específico del equipo
    # (puede ser Twin, Novus, o formato custom)
    payload_parser="TwinPayloadParser",

    # Configuración del parser
    parser_config={
        "variable_mapping": {
            "5000": "pulsos",
            "5001": "caudal_crudo",
            "5002": "nivel_crudo"
        },
        "error_codes": {...}
    }
)
```

### Ventajas de Nuestro MQTT

```
┌────────────────────────────────────────────────────────────┐
│  COMPARACIÓN: API del Proveedor vs Nuestro MQTT            │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Usando Twin API:                                          │
│  ├─ Equipo → Twin Cloud → Poll cada 5min → Nosotros       │
│  ├─ Latencia: ~5 minutos                                   │
│  ├─ Dependencia: Twin debe estar disponible                │
│  ├─ Costo: Posible cobro por API calls                    │
│  └─ Control: Limitado                                      │
│                                                             │
│  Usando Nuestro MQTT:                                      │
│  ├─ Equipo → MQTT SmartHydro (directo)                    │
│  ├─ Latencia: < 1 segundo                                 │
│  ├─ Dependencia: Ninguna (nosotros controlamos todo)      │
│  ├─ Costo: Solo infraestructura propia                    │
│  └─ Control: Total                                         │
│                                                             │
│  🎯 El PROCESAMIENTO es IDÉNTICO                           │
│     (porque usa el mismo FormulaEngine)                    │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

## 📊 RESUMEN DE ARQUITECTURA CORRECTA

### ✅ Qué DEBE existir

1. **FormulaEngine** - Motor universal de procesamiento
2. **CoreVariable** - Definición de todas las variables
3. **Provider Parsers** - Uno por fabricante/proveedor
4. **MQTT Propio** - Broker independiente
5. **TelemetryRecord** - Almacenamiento JSON dinámico

### ❌ Qué NO debe existir

1. ~~Módulos hardcodeados de caudal/nivel/totalizado~~
2. ~~Lógica de procesamiento duplicada~~
3. ~~Dependencia exclusiva de APIs de proveedores~~
4. ~~Códigos de error genéricos~~
5. ~~Variables con nombres fijos~~

---

## 🚀 DIFERENCIACIÓN DEL MERCADO

### Nuestro Enfoque Único

```
┌────────────────────────────────────────────────────────────┐
│  COMPETENCIA                                                │
├────────────────────────────────────────────────────────────┤
│  ├─ Código hardcodeado para cada tipo de sensor           │
│  ├─ Dependientes de las APIs de los fabricantes           │
│  ├─ Lógica duplicada en ingesta/reportes/alertas          │
│  ├─ Difícil agregar nuevas variables                      │
│  └─ Limitados a los sensores que ya soportan              │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  SMARTHYDRO                                                 │
├────────────────────────────────────────────────────────────┤
│  ✅ UN SOLO MOTOR (FormulaEngine) para TODO               │
│  ✅ Independientes (nuestro MQTT propio)                   │
│  ✅ Lógica unificada en todos los contextos                │
│  ✅ Agregar variables = configuración, NO código           │
│  ✅ Soportamos CUALQUIER equipo (solo definir parser)      │
│  ✅ El método se PROPAGA automáticamente a todo el sistema │
└────────────────────────────────────────────────────────────┘
```

---

## 📝 PLAN DE MIGRACIÓN

### Eliminar Módulos Hardcodeados

```bash
# Archivos a ELIMINAR:
api/telemetry/ingestion/controllers/processing/
├─ caudal.py      # ❌ ELIMINAR
├─ nivel.py       # ❌ ELIMINAR
├─ totalized.py   # ❌ ELIMINAR
└─ utils.py       # ❌ ELIMINAR (si solo tiene funciones hardcodeadas)
```

### Migrar a FormulaEngine

```python
# Para cada función hardcodeada, crear CoreVariable equivalente

# Antes (hardcodeado):
def process_caudal_variable(value):
    return value * 1.0 + 0.0

# Después (dinámico):
CoreVariable.objects.create(
    internal_code="caudal_ls",
    operation="FORMULA",
    formula="{valor_crudo} * {scale} + {offset}",
    context={"scale": 1.0, "offset": 0.0}
)
```

---

**FIN DE LA ARQUITECTURA**
