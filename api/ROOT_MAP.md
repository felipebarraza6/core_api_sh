# SmartHydro: ROOT_MAP (AI Navigation Master)

Bienvenido, Agente. Este archivo es tu mapa maestro para entender SmartHydro. Úsalo para localizar lógica rápidamente sin escanear todo el árbol de archivos.

> [!NOTE]
> Para la visión global del sistema (Docker, Infra, Seguridad), consulta el [Global Master Architect](file:///Users/felipebarraza/projects/core_api_sh/__init__.md).

## 🧩 Provider Taxonomy (The "Three Layers" Rule)

Para evitar confusión, el sistema distingue tres tipos de "Proveedores":

| Capa             | Ubicación             | Rol Principal                         | Ejemplos                              |
| :--------------- | :-------------------- | :------------------------------------ | :------------------------------------ |
| **Ingestion**    | `telemetry.providers` | **Trae** datos de sensores hacia SH.  | MQTT (Novus/Netra), APIs de terceros. |
| **Integrations** | `api.providers`       | APIs de **servicios** no-IoT.         | Clima, Pronósticos, Mapas.            |
| **Compliance**   | `compliance`          | **Envía** datos a entes regulatorios. | API DGA, SMA.                         |

---

## 🗺️ Project Architecture Roadmap

| Funcionalidad               | App Django       | Directorio Clave        | Objetivo                                         |
| :-------------------------- | :--------------- | :---------------------- | :----------------------------------------------- |
| **Ingestión de Datos**      | `telemetry`      | `telemetry/ingestion/`  | Recepción de MQTT y HTTP de sensores.            |
| **Cálculos y Fórmulas**     | `telemetry`      | `telemetry/processing/` | Motor de fórmulas dinámicas (`FormulaEngine`).   |
| **CRM y Proyectos**         | `crm`            | `crm/`                  | Gestión de clientes, costos y tareas técnicas.   |
| **Servicios Core**          | `core`           | `core/services/`        | Lógica transversal, auth y utilidades globales.  |
| **Infraestructura IoT**     | `infrastructure` | `infrastructure/`       | Hardware físico (Devices/Models) y MQTT Brokers. |
| **Inteligencia Artificial** | `chatbot`        | `chatbot/`              | Motor LLM, herramientas y comandos interactivos. |
| **Cumplimiento Legal**      | `compliance`     | `compliance/`           | Reportes para DGA/SMA y normativa regulatoria.   |
| **Integraciones Externas**  | `providers`      | `providers/`            | Conectores con APIs de terceros y clima.         |
| **Gestión Documental**      | `documents`      | `documents/`            | Almacenamiento de planos, PDFs y certificados.   |
| **Comunicaciones**          | `notifications`  | `notifications/`        | Despacho de Email, WhatsApp y alertas.           |
| **SaaS y Licencias**        | `subscriptions`  | `subscriptions/`        | Gestión de planes, cuotas y suscripciones.       |
| **Mesa de Ayuda**           | `support`        | `support/`              | Ticketing y soporte técnico a usuarios.          |

## 📚 Glosario de Términos (Domain Knowledge)

- **CatchmentPoint (Punto de Captación)**: La entidad central. Representa un pozo físico o punto de medición.
- **FormulaEngine**: El corazón del sistema. Procesa variables 'raw' para convertirlas en métricas útiles (caudal, nivel).
- **SeparateDatabaseAndState**: Patrón usado en migraciones para manejar tablas compartidas entre apps.

## 🏗️ Technical Flows (How things move)

1.  **Incoming Data**: `MQTTSubscriberService` → `MQTTPayloadParser` → `unified_processing.save_telemetry_data`.
2.  **Calculations**: `FormulaEngine` resolves variables in `TelemetryRecord.data` using configs.
3.  **Outgoing Compliance**: `save_telemetry_data` → `send_compliance_data` (Celery) → `ComplianceService` → External Agency.

## ⚠️ Legacy & Cleanup Status

| Item                             | Status        | Action / Warning                                  |
| :------------------------------- | :------------ | :------------------------------------------------ |
| `api.core.tasks.dga`             | **LEGACY**    | Do not use. Replaced by `compliance_unified`.     |
| `api.core.tasks.sma`             | **LEGACY**    | Do not use. Replaced by `compliance_unified`.     |
| `api.telemetry.admin_compliance` | **LEGACY**    | Use `api.compliance.admin` instead.               |
| Hardcoded Credentials            | **FORBIDDEN** | Use `SystemConfiguration` or `auth_config` in DB. |

## 🚦 AI Behavioral Rules

1.  **Always read the `__init__.md`** inside an app before modifying its models or views.
2.  **Act as the Mini-Agent**: Adopta el rol y las **AI Specialist Skills** definidas en el `__init__.md` del módulo.
3.  **No Hardcoding**: Toda configuración lógica debe ser dinámica via `FormulaEngine` o `PayloadParsingRule`.
4.  **Database Decoupling**: Mantén la separación entre Ingestión (`telemetry`) e Integración (`compliance`).
5.  **Atomic Migrations**: Usa el patrón `SeparateDatabaseAndState` si mueves modelos entre apps.

---
*Para más detalle, ver [GEMINI.md](file:///Users/felipebarraza/projects/core_api_sh/GEMINI.md)*
