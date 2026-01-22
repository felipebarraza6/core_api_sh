# crm: __init__ & AI SKILLS

Gestión de la capa de negocio y operaciones técnicas de SmartHydro.

## 🎯 Purpose & Scope
Manejo de Clientes, Proyectos, Costos operativos y Trazabilidad de tareas técnicas. Es el puente entre los datos técnicos y la gestión comercial.

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar aquí, asume el rol de **Operations & CRM Specialist**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | Los costos deben desglosarse por `Project`. Nunca uses costos globales. |
| **Restriction** | La eliminación de `Client` debe ser lógica o protegida si tiene proyectos activos. |
| **Tooling** | Usa los mixins de `ModelApi` para tracking de quién modificó cada entidad. |

### 🛠️ Standard Workflows
1. **Onboarding Client**: Crear `Client` -> Crear `Project` -> Vincular `CatchmentPoints` de telemetría.
2. **Task Tracking**: Registrar `Task` vinculada a proyecto -> Adjuntar `Document` si es necesario.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`Client` / `BusinessUnit`**: La estructura jerárquica de la cuenta.
- **`Project`**: El contenedor de operaciones y telemetría contratada.
- **`Task` / `Cost`**: Gestión operativa diaria.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
