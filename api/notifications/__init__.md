# notifications: __init__ & AI SKILLS

Este es un resumen estructural de la aplicación `notifications`. Úsalo para gestionar comunicaciones automáticas (Email, WhatsApp, Push).

## 🎯 Purpose & Scope
Motor de mensajería del sistema. Recibe alertas de telemetría o eventos de CRM y los distribuye a través de diferentes canales (Email, WhatsApp, App).

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar en esta carpeta, asume el rol de **Communications Architect**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | Una alerta gatilla N mensajes via `signal` de `telemetry`. |
| **Restriction** | Nunca hardcodees texto; usa `NotificationTemplate`. |
| **Tooling** | Integración con `Twilio` para WhatsApp y `SendGrid` para Email. |

### 🛠️ Standard Workflows
1. **New Notification**: Crear template -> Definir triggers -> Probar envío en entorno staging.
2. **Review Logs**: Revisar `NotificationLog` para verificar tasas de entrega.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`NotificationLog`**: Historial de envíos.
- **`Template`**: Contenido y variables para cada canal.
- **`UserConfiguration`**: Preferencias de recepción del usuario.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
