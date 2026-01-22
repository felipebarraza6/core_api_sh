# providers: __init__ & AI SKILLS

Este es un resumen estructural de la aplicación `providers`. Úsalo para integraciones con APIs externas y servicios de terceros.

## 🎯 Purpose & Scope
Capa de abstracción para servicios externos (Clima, APIs gubernamentales, otros brokers). Centraliza las conexiones que no son hardware propio.

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar en esta carpeta, asume el rol de **External Integration Lead**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | Toda llamada externa DEBE tener logs detallados de payload y response. |
| **Restriction** | Nunca guardes API Keys directamente; usa `settings` o env vars. |
| **Tooling** | Usa `Postman` o `curl` para validar el endpoint antes de codear en Python. |

### 🛠️ Standard Workflows
1. **New Provider**: Heredar de clase base para API -> Implementar auth -> Implementar fetch de datos.
2. **Maintenance**: Revisar `last_sync` y rotar credenciales si es necesario.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`ExternalProvider`**: Configuración de acceso a servicios externos.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
