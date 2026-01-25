# 🏭 Ingestion App (Connectivity Layer)

**Responsabilidad**: Gestionar toda la conectividad con el mundo exterior (Sensores, APIs, Brokers).
**Estado**: ✅ ACTIVO (Nueva Arquitectura)

## 🧠 Propósito
Aislar la lógica de "Conectividad" (que es propensa a errores de red y timeouts) del "Núcleo de Datos" (Telemetry). Si el MQTT se cae, solo falla esta app, no la base de datos histórica.

## 📦 Componentes Clave

1.  **`services/provider_manager.py`**:
    *   Cerebro central.
    *   Carga proveedores dinámicamente.
    *   Decide qué `Handler` usar para cada punto.
    
2.  **`mqtt/broker.py`**:
    *   Servicio de Broker interno (Mosquitto wrapper).
    *   Escucha topics y enruta mensajes.

3.  **`services/provider_handlers.py`**:
    *   `DynamicAPIHandler`: Para proveedores REST/HTTP (ej: Tago, Nettra).
    *   `MQTTProviderHandler`: Para proveedores MQTT.

## 🔄 Flujo de Datos
1.  **Input**: Datos crudos llegan por MQTT o API Fetch.
2.  **Proceso**: Se normalizan a un diccionario estándar `{'value': X, 'timestamp': Y}`.
3.  **Output**: Se envían a `api.telemetry` para ser procesados (fórmulas) y guardados.

## ⚠️ Dependencias
*   Usa modelos de `api.telemetry` (`TelemetryProvider`, `CatchmentPoint`) para configuración.
