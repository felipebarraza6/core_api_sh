# compliance: __init__ & AI SKILLS

Este es un resumen estructural de la aplicación `compliance`. Úsalo para gestionar normativas y reportes regulatorios (DGA, SMA).

## 🎯 Purpose & Scope
Capa de cumplimiento normativo. Se encarga de transformar la telemetría en reportes legales y asegurar que la transmisión a entes gubernamentales sea correcta.

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar en esta carpeta, asume el rol de **Regulatory Compliance Expert**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | Las métricas legales requieren 4-6 decimales de precisión. |
| **Restriction** | Nunca modifiques registros en `ManualComplianceRecord` sin una auditoría de usuario. |
| **Tooling** | Valida formatos JSON contra los esquemas oficiales de la DGA. |

### 🛠️ Standard Workflows
1. **Configuring Point**: Crear `PointComplianceConfig` -> Vincular a `ComplianceStandard` -> Validar transmisión.
2. **Auditing**: Cruzar `TelemetryRecord` con `ManualComplianceRecord` para detectar discrepancias.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`ComplianceStandard`**: Define las reglas de la norma (ej: "DGA 2.0").
- **`PointComplianceConfig`**: Configuración específica de un punto para una norma.

### Service Layer / Logic
- **`transmitters/` (planned)**: Clientes API para DGA/SMA.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
