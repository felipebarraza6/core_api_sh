# telemetry.providers: Ingestion Specialist

Este módulo gestiona la entrada de datos desde el mundo exterior hacia SmartHydro.

## 🎯 Telemetry Provider vs Compliance Provider

Es vital entender la diferencia para no duplicar lógica:

1.  **Telemetry Provider (Este módulo)**:
    *   **Rol**: RECOGIDA de datos (Ingestion).
    *   **Dirección**: Mundo Exterior (Sensor/Broker/API) -> SmartHydro.
    *   **Ejemplos**: MQTT de Novus, API de Nettra, ModBus de PLC.
    *   **Meta**: Obtener el dato crudo y guardarlo en `TelemetryRecord`.

2.  **Compliance Provider (`api/compliance`)**:
    *   **Rol**: ENTREGA de datos (Regulatory Delivery).
    *   **Dirección**: SmartHydro -> Gobierno/DGA/SMA.
    *   **Ejemplos**: API DGA v2, Portal SMA.
    *   **Meta**: Tomar datos validados y cumplir con la ley.

## 🧠 AI Specialist Skills

| Skill | Description |
| :--- | :--- |
| **MQTT Service** | Usa siempre `service_identifier` para agrupar tópicos. |
| **Parsing Rules** | Prefiere `jsonpath` sobre scripts Python por seguridad y rendimiento. |
| **Failover** | Configura `priority` en `CatchmentPointProvider` para redundancia. |

## 🛠️ Dynamic MQTT Workflow
Para habilitar un nuevo servicio tipo `mqtt/netra`:
1. Crea un `TelemetryProvider` llamado "Netra MQTT".
2. Configura su `MQTTProviderConfig` con `service_identifier="netra"`.
3. Define tópicos en `subscribe_topic_template` (ej: `netra/{device_id}/data`).
4. Añade `PayloadParsingRule` para extraer los campos `flow`, `total`, etc.
