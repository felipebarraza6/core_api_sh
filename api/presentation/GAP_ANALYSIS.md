# 🧪 Análisis de Brechas para Testing (Gap Analysis)

**Fecha**: 24 Enero 2026

Este documento detalla el estado actual de cada aplicación con miras a la preparación de pruebas automatizadas (Unitarias e Integración).

## 🟢 1. App: Ingestion (Conectividad)
**Estado**: LISTO PARA TEST (Mocks requeridos)

*   **Lo que hay**:
    *   `DynamicMQTTHandler` completo con reconexión y parsing.
    *   `DynamicAPIHandler` con soporte para REST/HTTP.
    *   `MQTTPayloadParser` con lógica de Templates, JSONPath y Regex.
*   **Lo que falta (Brechas)**:
    *   **Tests de Broker**: No tenemos un broker MQTT real en el CI/CD. Se requiere `mock.patch` para `paho.mqtt.client`.
    *   **Redis Cache**: `_perform_login_auth` tiene un TODO para usar Redis real. Ahora hace login en cada request si no hay caché.
    *   **Validación SSL**: No se ha probado la conexión TLS con certificados reales.

## 🟡 2. App: Documents (DocGen)
**Estado**: PARCIALMENTE LISTO

*   **Lo que hay**:
    *   Modelos `DocumentTemplate`, `ScheduledGeneration`.
    *   Motor `DocumentGenerator` con lógica de reemplazo.
*   **Lo que falta**:
    *   **Librerías Reales**: El código tiene `try/except ImportError` para `docxtpl` y `openpyxl`. Si el entorno de test no las instala, el generador hará una "copia simple" del archivo.
    *   **PDF real**: La generación de PDF hoy retorna un HTML. Falta integrar `WeasyPrint` o similar si se requiere binario real.

## 🟢 3. App: Telemetry (Data Core)
**Estado**: LISTO PARA TEST

*   **Lo que hay**:
    *   Modelos de datos (`TelemetryRecord`, `CatchmentPoint`) estables.
    *   `FormulaEngine` (no tocado en este refactor, se asume estable).
*   **Riesgos**:
    *   Las migraciones de `providers` viven aquí, pero la lógica se fue a `ingestion`. Validar que `admin.py` no importe cosas que ya no existen.

## 🟡 4. App: Unified (Dashboard)
**Estado**: REVISIÓN REQUERIDA

*   **Hallazgo**: Se encontraron `TODO`s en `dashboard.py` relacionados con la agregación de alertas.
*   **Impacto**: El endpoint `/api/dashboard/` podría devolver datos incompletos o mockeados.

## 📋 Plan de Acción para Testing

1.  **Prioridad 1 (Ingestion)**: Crear `tests/test_mqtt_parser.py`. Es lógica pura (sin I/O) y crítica.
2.  **Prioridad 2 (Documents)**: Configurar `requirements-test.txt` con `docxtpl` y crear un test que suba un `.docx` dummy y verifique el output.
3.  **Prioridad 3 (Integration)**: Testear el flujo completo: `Ingestion (Mock MQTT)` -> `Telemetry Record` -> `Unified Dashboard`.
