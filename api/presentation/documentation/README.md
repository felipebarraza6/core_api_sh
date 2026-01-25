# 📚 SmartHydro Technical Documentation

This directory contains deep-dive technical documentation, implementation details, and templates.

## 🛠️ Technical Internal Guides (`technical/`)

*   **[MQTT Subscriber Guide](technical/GUIDE_MQTT.md)**:
    *   Arquitectura "3-Layers" de ingesta MQTT.
    *   Cómo configurar Mosquitto, Topics y Parsing Rules dinámicas.
    *   Troubleshooting de mensajes no recibidos.

*   **[Telemetry Engine Internals](technical/TELEMETRY_ENGINE_INTERNALS.md)**:
    *   Explicación profunda del `FormulaEngine`.
    *   Comparativa Legacy vs New Architecture.
    *   Flujo de vida de un dato (Ingest -> Process -> Store).

*   **[Document Generation Engine](technical/DOCUMENT_GENERATION.md)**:
    *   Cómo crear Templates Word/Excel (`{{variable}}`).
    *   Cómo programar reportes automáticos (Cron).

## 📄 Templates (`templates/`)

*   **[Overview Template](templates/OVERVIEW_TEMPLATE.md)**:
    *   Plantilla estándar para documentar nuevos módulos/apps.

---
*Volver a [System Architecture](../API_ARCHITECTURE.md)*
