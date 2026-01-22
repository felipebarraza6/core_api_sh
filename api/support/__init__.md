# support: __init__ & AI SKILLS

Este es un resumen estructural de la aplicación `support`. Úsalo para gestionar la mesa de ayuda y tickets técnicos.

## 🎯 Purpose & Scope
Sistema de soporte interno y para clientes. Permite reportar fallos de hardware, solicitar cambios de configuración o soporte técnico general.

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar en esta carpeta, asume el rol de **Support Operations Lead**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | Todo `Ticket` sin asignar debe enviar alerta a los admins. |
| **Restriction** | Un ticket cerrado no puede recibir comentarios nuevos (debe reabrirse). |
| **Tooling** | Integrar `Category` con `KnowledgeBase` para sugerencias automáticas. |

### 🛠️ Standard Workflows
1. **Ticket Lifecycle**: Open -> Assigned -> In Progress -> Resolved -> Closed.
2. **Escalation**: Si el ticket es de "Hardware", vincular automáticamente con el `Device` afectado.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`Ticket`**: El incidente o requerimiento.
- **`Comment`**: Hilo de conversación del soporte.
- **`Category`**: Tipificación del problema (ej: "Hardware", "Software").

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
