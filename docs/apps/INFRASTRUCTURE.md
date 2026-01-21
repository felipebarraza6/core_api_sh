# App Infrastructure - Gestión de Dispositivos IoT

**Propósito:** Gestionar dispositivos físicos de telemetría (sensores, dataloggers, PLCs)

---

## Modelos

### 1. Manufacturer (Fabricante/Proveedor)

Empresas que fabrican los dispositivos (Novus, Siemens, NXPerience, etc.)

| Campo | Tipo | Descripción |
|:------|:-----|:------------|
| `name` | CharField | Nombre del fabricante |
| `code` | CharField | Código único (ej: NOVUS, SIEMENS) |
| `mqtt_broker_host` | CharField | Broker MQTT del fabricante |
| `integration_status` | CharField | Estado de integración |

**Ejemplo:**
```python
Manufacturer(
    name="Novus Automation",
    code="NOVUS",
    mqtt_broker_host="mqtt.novus.com.br",
    integration_status="PRODUCTION"
)
```

---

### 2. DeviceModel (Modelo de Dispositivo)

Modelos específicos de dispositivos

| Campo | Tipo | Descripción |
|:------|:-----|:------------|
| `manufacturer` | FK | Fabricante |
| `model_name` | CharField | Nombre del modelo |
| `model_code` | CharField | Código del modelo |

**Ejemplo:**
```python
DeviceModel(
    manufacturer=novus,
    model_name="Datalogger NXPerience",
    model_code="NXP-001"
)
```

---

### 3. Device (Dispositivo Físico)

Dispositivos IoT instalados en campo

| Campo | Tipo | Descripción |
|:------|:-----|:------------|
| `device_id` | CharField | ID único (MAC, Serial) |
| `name` | CharField | Nombre descriptivo |
| `catchment_point` | FK | Punto de captación |
| `device_model` | FK | Modelo del dispositivo |
| `status` | CharField | Estado actual |
| `last_seen` | DateTime | Última conexión |
| `battery_level` | Decimal | Nivel de batería (%) |

**Estados:**
- `ONLINE` - En línea
- `OFFLINE` - Fuera de línea
- `ERROR` - Con error
- `MAINTENANCE` - En mantenimiento
- `BATTERY_LOW` - Batería baja

**Ejemplo:**
```python
Device(
    device_id="00:1A:2B:3C:4D:5E",
    name="Sensor Pozo Norte",
    catchment_point=punto_norte,
    device_model=nxperience_model,
    status="ONLINE",
    battery_level=85.5
)
```

---

### 4. Connection (Conexión MQTT)

Conexiones MQTT activas por fabricante

| Campo | Tipo | Descripción |
|:------|:-----|:------------|
| `manufacturer` | FK | Fabricante |
| `connection_name` | CharField | Nombre de conexión |
| `broker_host` | CharField | Host del broker |
| `client_id` | CharField | ID del cliente MQTT |
| `status` | CharField | Estado de conexión |

---

## Relaciones

```
Manufacturer
 │
 ├─▶ DeviceModel (1:N)
 │    └─▶ Device (1:N)
 │         └─▶ CatchmentPoint (FK)
 │
 └─▶ Connection (1:N)
```

---

## Uso en el Sistema

### Flujo de Datos

1. **Fabricante** (Novus) tiene varios **Modelos** (NXPerience, Datalogger)
2. Cada **Modelo** tiene múltiples **Dispositivos** físicos instalados
3. Cada **Dispositivo** está asociado a un **CatchmentPoint**
4. Los datos fluyen: Device → CatchmentPoint → TelemetryRecord

### Ejemplo Completo

```python
# 1. Fabricante
novus = Manufacturer.objects.create(
    name="Novus Automation",
    code="NOVUS",
    mqtt_broker_host="mqtt.novus.com.br",
    mqtt_broker_port=1883,
    integration_status="PRODUCTION"
)

# 2. Modelo
nxp_model = DeviceModel.objects.create(
    manufacturer=novus,
    model_name="NXPerience Datalogger",
    model_code="NXP-5000"
)

# 3. Dispositivo
device = Device.objects.create(
    device_id="00:1A:2B:3C:4D:5E",
    name="Datalogger Pozo Norte",
    catchment_point=pozo_norte,
    device_model=nxp_model,
    status="ONLINE"
)

# 4. Conexión MQTT
connection = Connection.objects.create(
    manufacturer=novus,
    connection_name="Conexión Novus Principal",
    broker_host="mqtt.novus.com.br",
    broker_port=1883,
    client_id="smarthydro_novus_001",
    status="CONNECTED"
)
```

---

## Admin Django

Ahora disponible en `/admin/` en la sección **"Infraestructura IoT"**:

- **Proveedores de Equipos** - Gestionar fabricantes
- **Modelos de Equipos** - Gestionar modelos
- **Dispositivos IoT** - Gestionar dispositivos
- **Conexiones MQTT** - Gestionar conexiones

### Características del Admin

- **Manufacturer**: Filtros por estado de integración, contador de modelos
- **DeviceModel**: Filtros por fabricante, contador de dispositivos, inline de devices
- **Device**: Estados con colores, nivel de batería visual, búsqueda por ID
- **Connection**: Estados de conexión con indicadores visuales

---

## Relación con Otras Apps

| App | Relación |
|:----|:---------|
| **telemetry** | Device → CatchmentPoint (FK) |
| **providers** | Connection → TelemetryProvider (futuro) |
| **crm** | Manufacturer → Client (futuro, para ownership) |

---

## Próximas Mejoras

1. **Device Health Monitoring** - Alertas de batería baja
2. **Firmware Management** - Versionado de firmware por dispositivo
3. **Maintenance Schedule** - Calendario de mantenimiento
4. **Device Groups** - Agrupar dispositivos por tipo/ubicación
5. **Command Queue** - Enviar comandos a dispositivos

---

## Estado Actual

- ✅ Modelos definidos
- ✅ Admin funcional
- ✅ Relaciones con telemetry
- ⏳ API REST pendiente
- ⏳ Integración con MQTT subscriber pendiente
