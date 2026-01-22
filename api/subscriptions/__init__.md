# subscriptions: __init__ & AI SKILLS

Este es un resumen estructural de la aplicación `subscriptions`. Úsalo para gestionar planes SaaS y cuotas.

## 🎯 Purpose & Scope
Manejo comercial de la plataforma: Planes, renovaciones, control de cuotas de dispositivos y usuarios por licencia.

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar en esta carpeta, asume el rol de **SaaS Operations Specialist**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | Toda acción de creación (`Device`, `User`) debe validar el `QuotaManager`. |
| **Restriction** | Las fechas de expiración deben usar `UTC` para consistencia. |
| **Tooling** | Reportes de uso via CRM integrados con facturación. |

### 🛠️ Standard Workflows
1. **Upgrading Client**: Validar nuevo plan -> Actualizar `Subscription` -> Notificar a CRM.
2. **Quota Check**: Ejecutar middleware de validación en endpoints críticos.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`Plan`**: Definición de límites y precios.
- **`Subscription`**: El vínculo activo entre un Cliente y un Plan.
- **`UsageMetric`**: Tracking de consumo para planes variables.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
