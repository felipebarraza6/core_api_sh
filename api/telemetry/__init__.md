# telemetry: __init__ & AI SKILLS

La aplicación más crítica. Maneja la ingesta, procesamiento y almacenamiento de datos de sensores.

## 🎯 Purpose & Scope
Gestión del flujo de datos IoT: Recepción MQTT/HTTP, Motor de Fórmulas dinámicas, Almacenamiento histórico y Alertas preventivas.

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar aquí, asume el rol de **Telemetry & IoT Expert**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | **Prohibido hardcodear fórmulas**. Usa `FormulaEngine` y `TelemetryScheme`. |
| **Source vs Endpoint** | Diferencia entre `TelemetryProvider` (Source) y `ComplianceProvider` (Endpoint). |
| **Tooling** | El `FormulaEngine` es la única fuente de verdad para cálculos de variables. |

### 🛠️ Standard Workflows
1. **New Sensor Ingestion**: Definir `CatchmentPoint` -> Crear `TelemetryScheme` con fórmulas -> Validar entrada MQTT.
2. **Formula Debug**: Probar expresiones en el motor antes de aplicarlas a datos reales.
3. **Dynamic MQTT Service**: Crear `TelemetryProvider` -> Configurar `MQTTProviderConfig` con su `service_identifier` (ej: netra) -> Añadir `PayloadParsingRule`.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`CatchmentPoint`**: Gemelo digital del pozo o punto físico.
- **`TelemetryRecord`**: Datos procesados y finales.
- **`FormulaEngine`**: Motor lógico de procesamiento matemático.

### Key Logic Paths
- `telemetry/ingestion/`: Controladores de entrada de datos.
- `telemetry/processing/`: Lógica de cálculo y validación.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
