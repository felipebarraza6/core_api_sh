# 🎯 PROPUESTA: Arquitectura Clara de Ingesta de Datos

**Fecha:** 2026-01-22
**Estado:** DRAFT - Necesita aprobación
**Problema:** Confusión entre conceptos de equipos, proveedores y canales de comunicación

---

## 📊 SITUACIÓN ACTUAL (Confusa)

### Modelos Existentes

```
├─ Infrastructure (Legacy - 0 datos)
│  ├─ Device
│  ├─ Connection
│  ├─ DeviceModel
│  └─ Manufacturer
│
├─ Telemetry Providers (V3 - En uso)
│  ├─ TelemetryProvider (5 registros)
│  ├─ CatchmentPointProvider (1 registro)
│  ├─ MQTTProviderConfig (2 registros)
│  └─ PayloadParsingRule (3 registros)
│
└─ CatchmentPoint (1 registro)
```

### ❌ Problemas Identificados

1. **Device vs TelemetryProvider**: ¿Qué diferencia hay?
2. **MQTT Cliente vs MQTT Servidor**: Mismo modelo para casos opuestos
3. **CatchmentPoint**: ¿Es un punto físico o un equipo?
4. **point_code en CatchmentPointProvider**: ¿Es device_id?
5. **Infrastructure vacía**: 4 modelos sin datos pero con FKs en código

---

## 🎯 PROPUESTA: 3 CAPAS CLARAS

### CAPA 1: EQUIPOS FÍSICOS (Hardware)

**Concepto:** Dispositivos físicos que generan datos (sensores, PLCs, gateways)

```
📦 Device (mantener Infrastructure.Device)
   ├─ serial_number: "NXP-001-2024"
   ├─ manufacturer: FK → Manufacturer
   ├─ model: FK → DeviceModel
   ├─ location: Point (coordenadas)
   ├─ installation_date: Date
   └─ metadata: JSON (calibración, specs)

Ejemplo:
   • Serial: NXP-001-2024
   • Manufacturer: Novus
   • Model: NXperience
   • Location: Pozo El Roble
```

**Uso:**
- Inventario de hardware
- Mantenimiento
- Soporte técnico
- Garantías

---

### CAPA 2: PUNTOS DE MEDICIÓN (Lógicos)

**Concepto:** Punto lógico donde se captan datos (puede tener 1 o más devices)

```
📦 CatchmentPoint (ya existe)
   ├─ point_code: "POZO_001"
   ├─ title: "Pozo El Roble"
   ├─ location: Point
   ├─ owner_user: FK → User
   └─ devices: M2M → Device  # ← NUEVA relación

Ejemplo:
   • Code: POZO_001
   • Title: "Pozo El Roble"
   • Devices: [NXP-001-2024, PLC-002-2024]  # 2 equipos
```

**Uso:**
- Agrupación lógica de datos
- Permisos por punto
- Reporting
- Compliance (DGA)

---

### CAPA 3: PROVEEDORES DE DATOS (Canales)

**Concepto:** Canales por donde ENTRAN datos al sistema

#### 3A. Proveedores API REST

```
📦 TelemetryProvider (type="api")
   ├─ name: "nettra"
   ├─ display_name: "Nettra API"
   ├─ base_url: "https://api.nettra.cl"
   ├─ auth_method: "bearer"
   └─ endpoint_template: "/stations/{station_id}/data"

Ejemplo:
   • Proveedor: Nettra
   • Equipos: Se identifican por station_id
   • Flujo: SmartHydro → (pull) → API Nettra
```

#### 3B. Proveedores MQTT Externos

```
📦 TelemetryProvider (type="mqtt_client")
   ├─ name: "novus_mqtt"
   ├─ base_url: "mqtt://broker.novus.com:1883"
   ├─ mqtt_config:
   │  ├─ mode: "client"  # ← NUEVO campo
   │  ├─ broker_host: "broker.novus.com"
   │  └─ subscribe_topics: ["novus/+/data"]

Ejemplo:
   • Proveedor: Broker MQTT de Novus
   • Flujo: SmartHydro → (subscribe) → Broker Novus
   • Rol: Cliente MQTT
```

#### 3C. Broker MQTT Propio

```
📦 TelemetryProvider (type="mqtt_server")
   ├─ name: "smarthydro_broker"
   ├─ base_url: "mqtt://localhost:1883"
   ├─ mqtt_config:
   │  ├─ mode: "server"  # ← NUEVO campo
   │  ├─ broker_host: "mqtt_broker"
   │  ├─ topic_patterns: [
   │  │   "sh/{device_sn}/data",
   │  │   "interno/{device_sn}/data"
   │  │]
   │  └─ parsing_rules: FK → PayloadParsingRule

Ejemplo:
   • Proveedor: Broker local SmartHydro
   • Flujo: Equipos → (publish) → SmartHydro Broker → (listen) → SmartHydro
   • Rol: Servidor MQTT
```

---

## 🔗 RELACIONES

### Relación: Device ↔ CatchmentPoint

```
CatchmentPoint.devices = M2M → Device

Ejemplo:
   POZO_001 (CatchmentPoint)
      └─ Devices:
         ├─ NXP-001-2024 (Sensor caudal)
         └─ PLC-002-2024 (PLC maestro)
```

### Relación: CatchmentPoint ↔ TelemetryProvider

```
CatchmentPointProvider (tabla intermedia)
   ├─ point: FK → CatchmentPoint
   ├─ provider: FK → TelemetryProvider
   ├─ device: FK → Device  # ← NUEVO
   ├─ provider_device_id: "NXP-001-2024"  # ID en el proveedor
   ├─ priority: int
   └─ device_config: JSON

Ejemplo:
   POZO_001 (CatchmentPoint)
      └─ Providers:
         ├─ Nettra API
         │  ├─ device: NXP-001-2024
         │  ├─ provider_device_id: "station_123"
         │  └─ priority: 10 (primario)
         │
         └─ SmartHydro Broker (MQTT)
            ├─ device: NXP-001-2024
            ├─ provider_device_id: "NXP-001-2024"
            └─ priority: 5 (backup)
```

---

## 🎯 CASOS DE USO

### Caso 1: API REST de Nettra

```
1. Crear Device físico:
   • Serial: NETTRA-STA-123
   • Manufacturer: Nettra
   • Model: Station v2

2. Crear CatchmentPoint:
   • Code: POZO_NORTE_01
   • Devices: [NETTRA-STA-123]

3. Crear TelemetryProvider:
   • Type: api
   • Name: nettra
   • Base URL: https://api.nettra.cl

4. Relacionar:
   CatchmentPointProvider:
      • Point: POZO_NORTE_01
      • Provider: nettra
      • Device: NETTRA-STA-123
      • provider_device_id: "station_123"
      • Priority: 10

Resultado:
   SmartHydro consulta API Nettra cada X minutos
   GET /stations/station_123/data
```

### Caso 2: MQTT Propio (Equipos se conectan a ti)

```
1. Crear Device físico:
   • Serial: NXP-001-2024
   • Manufacturer: Novus
   • Model: NXperience

2. Configurar Device para publicar:
   • MQTT Broker: mqtt_broker:1883
   • Topic: sh/NXP-001-2024/data
   • Payload: {"flow": 10.5, "level": 2.3}

3. Crear TelemetryProvider (si no existe):
   • Type: mqtt_server
   • Name: smarthydro_broker
   • mqtt_config:
      • mode: "server"
      • topic_patterns: ["sh/{device_sn}/data"]

4. Crear CatchmentPoint:
   • Code: POZO_SUR_01
   • Devices: [NXP-001-2024]

5. Relacionar:
   CatchmentPointProvider:
      • Point: POZO_SUR_01
      • Provider: smarthydro_broker
      • Device: NXP-001-2024
      • provider_device_id: "NXP-001-2024"

Resultado:
   Equipo publica → Broker local → MQTTSubscriber escucha → Procesa
```

### Caso 3: MQTT Externo (Conectarse a broker de tercero)

```
1. Crear Device físico:
   • Serial: TWIN-GW-001
   • Manufacturer: Twin
   • Model: Gateway

2. Crear TelemetryProvider:
   • Type: mqtt_client
   • Name: twin_mqtt
   • mqtt_config:
      • mode: "client"
      • broker_host: "broker.twin.com"
      • subscribe_topics: ["twin/{device_id}/telemetry"]

3. Crear CatchmentPoint:
   • Code: POZO_ESTE_01
   • Devices: [TWIN-GW-001]

4. Relacionar:
   CatchmentPointProvider:
      • Point: POZO_ESTE_01
      • Provider: twin_mqtt
      • Device: TWIN-GW-001
      • provider_device_id: "GW-001"

Resultado:
   SmartHydro se conecta como cliente a broker.twin.com
   Subscribe: twin/GW-001/telemetry
```

---

## 📋 CAMBIOS NECESARIOS

### 1. Mantener Infrastructure (no eliminar)

- ✅ Mantener `Device`, `DeviceModel`, `Manufacturer`
- ✅ Usar para inventario de hardware físico
- ✅ Es concepto DIFERENTE a TelemetryProvider

### 2. Agregar campo `mode` a MQTTProviderConfig

```python
class MQTTProviderConfig:
    MQTT_MODES = [
        ('client', 'Cliente MQTT (conectar A broker externo)'),
        ('server', 'Servidor MQTT (escuchar broker local)'),
    ]
    mode = models.CharField(
        max_length=10,
        choices=MQTT_MODES,
        default='server',
        help_text="Rol MQTT: cliente (conectar) o servidor (escuchar)"
    )
```

### 3. Agregar relación Device en CatchmentPointProvider

```python
class CatchmentPointProvider:
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Dispositivo físico asociado (opcional)"
    )
```

### 4. Renombrar `point_code` → `provider_device_id`

```python
class CatchmentPointProvider:
    # Antes
    point_code = "DEVICE_001"

    # Después
    provider_device_id = "station_123"  # ID en el sistema del proveedor
    device = FK → Device(serial="NXP-001-2024")  # Device físico real
```

### 5. Separar tipos MQTT

```python
class TelemetryProvider:
    PROVIDER_TYPES = [
        ('api', 'REST API'),
        ('mqtt_client', 'MQTT Client (conectar a externo)'),
        ('mqtt_server', 'MQTT Server (broker local)'),
        ('modbus', 'ModBus TCP'),
        ('websocket', 'WebSocket'),
    ]
```

---

## 🎓 GLOSARIO FINAL

| Concepto | Qué ES | Ejemplo |
|----------|--------|---------|
| **Device** | Hardware físico | Sensor Novus NXP-001-2024 |
| **CatchmentPoint** | Punto lógico de medición | Pozo El Roble |
| **TelemetryProvider** | Canal de entrada de datos | API de Nettra, Broker MQTT |
| **CatchmentPointProvider** | Relación punto-proveedor-equipo | Pozo El Roble usa Nettra API para leer NXP-001 |
| **MQTTProviderConfig** | Configuración MQTT (cliente o servidor) | Conectar a broker.novus.com:1883 |

---

## ✅ VENTAJAS DE ESTA ARQUITECTURA

1. **Claridad**: Cada modelo tiene un propósito único
2. **Flexibilidad**: 1 punto puede tener múltiples devices y providers
3. **Failover**: Provider con priority alta/baja
4. **Trazabilidad**: Se sabe qué device físico generó cada dato
5. **Mantenimiento**: Gestión de hardware separada de ingesta
6. **MQTT claro**: mode="client" vs mode="server"

---

## 🚀 SIGUIENTE PASO

**Aprobar o ajustar esta propuesta antes de implementar**

Preguntas para definir:
1. ¿Te hace sentido esta separación Device / Point / Provider?
2. ¿El campo `mode` en MQTT resuelve la confusión?
3. ¿Necesitas ajustar algo más?
