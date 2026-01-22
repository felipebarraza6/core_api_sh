# Guía de Arquitectura y Telemetría de SmartHydro

## 1. Visión General
El sistema de telemetría de SmartHydro está diseñado para ser **agnóstico al proveedor**, **ultra-seguro** y **altamente escalable**. Unifica datos de varias fuentes (MQTT, APIs, PLCs) en un modelo de datos único y consistente.

## 2. Componentes Principales

### 2.1. Proveedores (`api/telemetry/providers`)
Este módulo maneja la conexión y la adquisición de datos crudos desde dispositivos externos.

*   **`TelemetryProvider`**: Representa un servicio o protocolo externo (ej: "DGA API", "Mosquitto MQTT", "Sercotec PLC").
*   **`CatchmentPointProvider`**: El enlace entre un proveedor y un `CatchmentPoint` (punto hidrológico) específico. Define *cómo* un punto específico obtiene datos de ese proveedor (ej: ID de sensor específico).
*   **`CatchmentPointMQTT`** (Extensión Dinámica): Configuración específica para dispositivos MQTT, permitiendo topics personalizados (`telemetry/{device_id}`) y reglas de parsing por dispositivo.

### 2.2. Ingesta y Procesamiento (`api/telemetry/ingestion`)
El "cerebro" que normaliza los datos crudos.

1.  **Datos Crudos**: Llegan vía `MQTTSubscriberService` o pollers de API.
2.  **Parsing**: `MQTTPayloadParser` o handlers específicos convierten bytes/JSON crudos en un diccionario estandarizado.
3.  **Procesamiento Unificado** (`unified_processing.py`):
    *   **Mapeo**: Mapea claves del proveedor (ej: "v1", "flow_rate") a campos internos (`flow`, `nivel`).
    *   **Transformación**: Aplica factores de escala, offsets y conversiones de unidades.
    *   **Validación**: Verifica rangos mínimos/máximos.

### 2.3. Modelos de Datos (`api/telemetry/models`)

#### `CatchmentPoint` (El Corazón)
Representa una ubicación física (pozo, estación de río, canal).
*   Centraliza toda la configuración.
*   Enlaza con `Infrastructure` (Dispositivos).

#### `CoreVariable` (La Configuración)
Define **qué** se mide en un punto.
*   `type_variable`: El tipo canónico (ej: `CAUDAL`, `NIVEL`).
*   `operation`: Puede ser `PHYSICAL` (sensor), `CALCULATED` (fórmula) o `VIRTUAL`.
*   `internal_code`: Identificador único para la variable en ese punto.

#### `TelemetryRecord` (Los Datos)
La única fuente de verdad para datos hidrológicos.
*   `timestamp`: Cuándo ocurrió la medición.
*   `data`: JSONField conteniendo los valores normalizados:
    ```json
    {
      "flow": 2.5,
      "total": 1250.7,
      "nivel": 12.3
    }
    ```
*   `compliance_status`: Rastrea si este registro ha sido enviado a DGA/SMA.

## 3. Flujo de Datos: Ejemplo MQTT

1.  **Dispositivo** publica en `telemetry/DEVICE_001`.
2.  **`MQTTSubscriberService`** recibe el mensaje.
3.  **Parsea** el payload usando reglas de `MQTTProviderConfig`.
4.  **Identifica** el `CatchmentPoint` asociado con `DEVICE_001`.
5.  **`DynamicMQTTHandler`** crea un diccionario de estandarización.
6.  **`save_telemetry_data`** verifica los datos contra reglas de `CoreVariable` (min/max).
7.  **Guarda** un nuevo `TelemetryRecord`.
8.  **Activa** cualquier alerta en tiempo real o tareas de cumplimiento.

## 4. Archivos Clave
*   `api/telemetry/models/telemetry.py`: Estructura de datos central (`TelemetryRecord`).
*   `api/telemetry/providers/mqtt_handler.py`: Lógica para conexión MQTT y mapeo.
*   `api/telemetry/ingestion/controllers/unified_processing.py`: El guardián para guardar datos.
