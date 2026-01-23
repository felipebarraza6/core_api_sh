# telemetry.providers: Ingestion Specialist

Este módulo gestiona la entrada de datos desde el mundo exterior hacia SmartHydro.

---

## 🎯 Arquitectura de Ingesta (3 Capas)

### CAPA 1: EQUIPOS FÍSICOS
**Modelo:** `Device` (`api.infrastructure.models`)
- Serial, Manufacturer, Model
- Inventario de hardware físico
- Gestión de mantenimiento

### CAPA 2: PUNTOS DE MEDICIÓN
**Modelo:** `CatchmentPoint` (`api.telemetry.models`)
- Punto lógico (pozo, estación)
- Puede tener múltiples devices
- Agrupación para compliance

### CAPA 3: PROVEEDORES DE DATOS
**Modelo:** `TelemetryProvider` (este módulo)
- Canal de ingesta de datos
- Tipos: API REST, MQTT Client, MQTT Server, ModBus

---

## 🔗 Relación: Device ↔ Point ↔ Provider

```
CatchmentPoint "POZO_001"
   └─ Providers (via CatchmentPointProvider)
      ├─ Nettra API
      │  ├─ device: NXP-001-2024 (Device físico)
      │  ├─ provider_device_id: "station_123" (ID en Nettra)
      │  └─ priority: 10 (primario)
      │
      └─ SmartHydro MQTT Server
         ├─ device: NXP-001-2024 (mismo equipo)
         ├─ provider_device_id: "NXP-001-2024" (serial)
         └─ priority: 5 (backup)
```

---

## 📡 Tipos de Provider

### 1. API REST
```python
TelemetryProvider(
    provider_type='api',
    base_url='https://api.nettra.cl',
    auth_method='bearer',
    endpoint_template='/stations/{device_id}/data'
)
```
**Uso:** Consumir API de terceros (Nettra, Novus, TTN)

### 2. MQTT Client (Conectar A broker externo)
```python
TelemetryProvider(
    provider_type='mqtt_client',
    base_url='mqtt://broker.novus.com:1883',
    mqtt_config={
        'mode': 'client',  # SmartHydro se conecta
        'service_identifier': 'novus',
        'subscribe_topics': ['novus/+/data']
    }
)
```
**Uso:** Consumir de broker MQTT de terceros

### 3. MQTT Server (Escuchar broker local)
```python
TelemetryProvider(
    provider_type='mqtt_server',
    base_url='mqtt://mqtt_broker:1883',
    mqtt_config={
        'mode': 'server',  # Equipos publican hacia SmartHydro
        'service_identifier': 'smarthydro',
        'subscribe_topics': ['sh/{device_id}/data']
    }
)
```
**Uso:** Equipos propios publican hacia SmartHydro

---

## 🎯 Telemetry Provider vs Compliance Provider

**NO CONFUNDIR:**

### Telemetry Provider (Ingesta)
- **Dirección:** Mundo Exterior → SmartHydro
- **Rol:** RECOGIDA de datos
- **Ejemplos:** API Nettra, Broker Novus, MQTT propio
- **Meta:** Obtener dato crudo → `TelemetryRecord`

### Compliance Provider (Salida)
- **Dirección:** SmartHydro → Gobierno (DGA/SMA)
- **Rol:** ENTREGA de datos
- **Ejemplos:** API DGA v2, Portal SMA
- **Meta:** Cumplir con ley/compliance

---

## ⚙️ Dynamic Parsing Engine

El sistema usa un motor de parsing desacoplado para procesar payloads de diferentes proveedores sin tocar el código del servicio.

**Clase:** `MQTTPayloadParser` (`api.telemetry.providers.mqtt_parser`)
**Regla:** `PayloadParsingRule` (`api.telemetry.providers.mqtt_models`)

### Métodos de Parsing Soportados:
1.  **JMESPath (Recomendado)**: Extrae valores usando sintaxis JSON avanzada.
2.  **Template**: Mapeo directo de campos de texto.
3.  **Python Script**: Para transformaciones complejas (usar con precaución).

---

## 🧠 AI Specialist Skills

| Skill                  | Description                                                                         |
| :--------------------- | :---------------------------------------------------------------------------------- |
| **MQTT Mode**          | Diferencia `mode='client'` (conectar A) vs `mode='server'` (escuchar EN).           |
| **Parsing Rules**      | Prefiere `jsonpath` (JMESPath) sobre scripts Python por seguridad y mantenibilidad. |
| **Service Identifier** | Usa siempre `service_identifier` para agrupar tópicos MQTT de un mismo origen.      |
| **Failover**           | Configura `priority` en `CatchmentPointProvider` para redundancia de datos.         |
| **Device Mapping**     | Asegura que `provider_variable_key` coincida con la salida de `PayloadParsingRule`. |
---

## 🛠️ Workflow: Agregar Nuevo Proveedor

### Caso 1: API REST (ej: Nettra)

1. **Crear Device físico** (opcional):
```python
Device.objects.create(
    serial_number='NETTRA-STA-123',
    manufacturer=nettra_manufacturer,
    model=nettra_station_model
)
```

2. **Crear TelemetryProvider**:
```python
TelemetryProvider.objects.create(
    name='nettra',
    provider_type='api',
    base_url='https://api.nettra.cl',
    auth_method='bearer',
    endpoint_template='/stations/{device_id}/data'
)
```

3. **Relacionar con CatchmentPoint**:
```python
CatchmentPointProvider.objects.create(
    point=pozo_001,
    provider=nettra_provider,
    device=nettra_device,  # FK al Device físico
    provider_device_id='station_123',  # ID en Nettra
    priority=10
)
```

### Caso 2: MQTT Servidor (equipos propios)

1. **Crear Device físico**:
```python
Device.objects.create(
    serial_number='NXP-001-2024',
    manufacturer=novus,
    model=nxperience
)
```

2. **Crear TelemetryProvider** (si no existe):
```python
provider = TelemetryProvider.objects.create(
    name='smarthydro_broker',
    provider_type='mqtt_server',
    base_url='mqtt://mqtt_broker:1883'
)

MQTTProviderConfig.objects.create(
    provider=provider,
    mode='server',  # Escuchar broker local
    service_identifier='smarthydro',
    subscribe_topic_template='sh/{device_id}/data'
)
```

3. **Configurar equipo** para publicar:
```
Broker: mqtt_broker:1883
Topic: sh/NXP-001-2024/data
Payload: {"flow": 10.5, "level": 2.3}
```

4. **Relacionar con CatchmentPoint**:
```python
CatchmentPointProvider.objects.create(
    point=pozo_001,
    provider=smarthydro_broker,
    device=nxp_device,
    provider_device_id='NXP-001-2024',  # Serial del equipo
    priority=5
)
```

---

## 📋 Campos Clave en CatchmentPointProvider

| Campo                | Tipo                   | Descripción                                    |
| -------------------- | ---------------------- | ---------------------------------------------- |
| `point`              | FK → CatchmentPoint    | Punto lógico de captación                      |
| `provider`           | FK → TelemetryProvider | Proveedor/canal de datos                       |
| `device`             | FK → Device            | Dispositivo físico (opcional)                  |
| `provider_device_id` | CharField              | ID del dispositivo en el sistema del PROVEEDOR |
| `priority`           | Integer                | Orden de failover (mayor = preferido)          |
| `device_config`      | JSON                   | Config del dispositivo (calibración, offset)   |
| `config_override`    | JSON                   | Override de config del proveedor               |

---

## 🚀 Ventajas de Esta Arquitectura

1. **Claridad**: Device (físico) ≠ Point (lógico) ≠ Provider (canal)
2. **Flexibilidad**: 1 punto puede tener múltiples devices y providers
3. **Failover**: Priority define orden de preferencia
4. **Trazabilidad**: Device FK permite saber qué hardware generó el dato
5. **MQTT claro**: `mode='client'` vs `mode='server'` elimina ambigüedad

---

**Ver también:** [PROPUESTA_ARQUITECTURA_INGESTA.md](../../../PROPUESTA_ARQUITECTURA_INGESTA.md)
