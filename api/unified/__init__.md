# 🌐 Unified API (Gateway Layer)

**Responsabilidad**: Exponer una interfaz única y estable (v0) para el Frontend, ocultando la complejidad interna.
**Estado**: ✅ ACTIVO

## 🧠 Propósito
Evitar que el Frontend tenga que consultar 5 apps distintas (CRM, Telemetry, Documents). La API Unificada agrega todo en respuestas JSON optimizadas.

## 📦 Componentes
*   `views_dashboard.py`: Endpoint `/dashboard` que entrega en una sola request:
    *   Alertas activas.
    *   Últimas mediciones.
    *   Estado de cumplimiento DGA.
*   `serializers`: Serializadores que combinan modelos de `core`, `telemetry` y `compliance`.
