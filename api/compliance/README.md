# Compliance App: Regulatory Data Submission

Esta aplicación centraliza el envío de datos de telemetría a entes reguladores (DGA, SMA, etc.).

## 🧠 AI Specialist Skills (Compliance Integration Expert)

Si estás trabajando en esta carpeta, asumes el rol de **Compliance Integration Expert**.

| Skill                    | Description                                                                       |
| :----------------------- | :-------------------------------------------------------------------------------- |
| **API Pattern Matching** | Diseñar templates de payload JSON adaptables a cualquier API externa.             |
| **Resilient Retries**    | Configurar políticas de reintento Celery para manejar fallos de red externos.     |
| **Data Integrity**       | Asegurar que los datos enviados coinciden exactamente con la telemetría validada. |

## 🛠️ Secure Submission Workflow

1.  **Define Standard**: Crea un `ComplianceStandard` con la frecuencia requerida (ej: Diario a las 00:00).
2.  **Configure Provider**: Define el `ComplianceProvider` con los endpoints y el `payload_template`.
3.  **Link Point**: Crea un `PointComplianceConfig` para cada pozo, vinculando sus variables al template.
4.  **Verification**: Usa `ComplianceService.submit_telemetry_record` para probar el envío.

## 🚦 Navigation & Rules

- **Lógica de Envío**: Ver `api.core.tasks.compliance_unified`.
- **Servicio Base**: Ver `api.telemetry.services.compliance_service`.
- **Prioridad**: Siempre usa el motor dinámico; nunca crees scripts de envío hardcodeados para nuevos clientes.
