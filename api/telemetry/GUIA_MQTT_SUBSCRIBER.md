# Guía: Configurar MQTT Subscriber para NXTRA/Novus

## 📡 Concepto

Tu broker MQTT **recibe datos** de dispositivos que se conectan a él:

```
Dispositivo NXTRA → PUBLICA → mqtt://tu-servidor:1883/nxtra/sensor01/data
                                        ↓
                              Django ESCUCHA y procesa
```

---

## 🎯 Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                  Dispositivos IoT                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  NXTRA   │  │  Novus   │  │  Nettra  │              │
│  │ Sensor01 │  │ Sensor02 │  │ Sensor03 │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
└───────┼─────────────┼─────────────┼─────────────────────┘
        │             │             │
        │ PUBLISH     │ PUBLISH     │ PUBLISH
        ↓             ↓             ↓
┌─────────────────────────────────────────────────────────┐
│          Mosquitto MQTT Broker (localhost:1883)        │
│                   Topics:                               │
│         nxtra/sensor01/data                             │
│         novus/sensor02/telemetry                        │
│         nettra/sensor03/metrics                         │
└─────────────────────┬───────────────────────────────────┘
                      │
                      │ SUBSCRIBE
                      ↓
┌─────────────────────────────────────────────────────────┐
│      MQTT Subscriber Service (Django)                  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  1. Escucha topics                                │  │
│  │  2. Parsea payload según reglas                   │  │
│  │  3. Procesa con FormulaEngine                     │  │
│  │  4. Guarda en TelemetryRecord                     │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Configuración Paso a Paso

### Paso 1: Crear Proveedor MQTT en Django Admin

1. Ir a **Admin → Telemetry Providers → Add TelemetryProvider**

```python
Name: mqtt_nxtra
Display Name: NXTRA MQTT
Type: mqtt
Base URL: # Dejar vacío (no se usa para subscriber)
Is Active: ✅
```

2. Crear **MQTTProviderConfig** asociado:

```python
Provider: mqtt_nxtra
Broker Host: localhost  # Tu broker local
Broker Port: 1883
Use TLS: ❌  # Para desarrollo

# Templates de topics
Subscribe Topic Template: "nxtra/{device_id}/data"
# Donde {device_id} será el código del punto

Default QoS: 1
Keep Alive: 60
```

---

### Paso 2: Crear Regla de Parsing

Ir a **Admin → Payload Parsing Rules → Add PayloadParsingRule**

#### Ejemplo para NXTRA con JSON:

```python
Provider: mqtt_nxtra
Name: NXTRA Standard JSON Parser
Rule Type: always  # O "topic_match" si necesitas filtrar

Parsing Method: jsonpath

Field Mappings:
{
  "flow": {
    "source": "$.data.flow",
    "type": "jsonpath"
  },
  "total": {
    "source": "$.data.total_m3",
    "type": "jsonpath"
  },
  "nivel": {
    "source": "$.data.water_level",
    "type": "jsonpath"
  },
  "timestamp": {
    "source": "$.timestamp",
    "type": "jsonpath"
  }
}

Validation Rules:
{
  "flow": {
    "min": 0,
    "max": 1000
  },
  "total": {
    "min": 0
  }
}
```

#### Ejemplo para Novus con formato custom:

```python
Provider: mqtt_novus
Name: Novus Binary Parser
Rule Type: topic_match
Rule Condition: {"pattern": "novus/.+/sensor"}

Parsing Method: python

Field Mappings:
{
  "pulses": "extract_pulses_from_binary(payload)",
  "timestamp": "extract_timestamp(payload)"
}
```

---

### Paso 3: Configurar Punto de Captación

1. Crear/editar tu **CatchmentPoint** normal

2. Crear **CatchmentPointMQTT** asociado:

```python
Point: [Tu punto de captación]
Provider: mqtt_nxtra

# Device ID personalizado (si el dispositivo usa otro ID)
Custom Device ID: sensor01  # Opcional, si no usa point_code

# Topics personalizados (opcional)
Custom Topics:
{
  "subscribe": "nxtra/sensor01/data"
}

# Configuración del dispositivo
Device Config:
{
  "calibration_factor": 1.23,
  "sensor_offset": 0.5
}

Is Active: ✅
```

---

### Paso 4: Configurar Variables

Asegúrate de que tu punto tenga **CoreVariable** configuradas:

```python
# En CatchmentPointProvider
Point: [Tu punto]
Variable: CAUDAL_INSTANTANEO
Variable Code: flow  # Debe coincidir con field_mappings
Provider Key: flow   # Opcional
Is Active: ✅

# Otra variable
Variable: TOTALIZADO
Variable Code: total
```

---

## 🏃 Ejecutar el Servicio

### Opción 1: Comando Django (Desarrollo)

```bash
docker exec -it smarthydro_django_dev python manage.py mqtt_subscriber start
```

Verás:
```
🚀 Iniciando MQTT Subscriber Service...
✅ Servicio iniciado exitosamente
   Broker: localhost:1883
   Puntos configurados: 3

⏳ Servicio corriendo... (Ctrl+C para detener)
```

### Opción 2: Celery Beat Task (Producción)

Agregar a `celeryconfig.py`:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'mqtt-subscriber-keepalive': {
        'task': 'api.telemetry.tasks.mqtt_subscriber_keepalive',
        'schedule': 60.0,  # Cada 60 segundos
    },
}
```

### Opción 3: Supervisor/Systemd (Producción Avanzada)

```ini
[program:mqtt_subscriber]
command=/app/manage.py mqtt_subscriber start
directory=/app
user=smarthydro
autostart=true
autorestart=true
stdout_logfile=/var/log/mqtt_subscriber.log
stderr_logfile=/var/log/mqtt_subscriber_error.log
```

---

## 📝 Formatos de Payload Soportados

### 1. JSON Simple

```json
{
  "device_id": "sensor01",
  "timestamp": "2026-01-20T15:30:00",
  "data": {
    "flow": 12.5,
    "total_m3": 1234.56,
    "water_level": 2.3
  }
}
```

**Parsing Rule:**
```python
parsing_method: "jsonpath"
field_mappings: {
  "flow": {"source": "$.data.flow", "type": "jsonpath"},
  "total": {"source": "$.data.total_m3", "type": "jsonpath"},
  "nivel": {"source": "$.data.water_level", "type": "jsonpath"}
}
```

---

### 2. JSON Flat

```json
{
  "id": "nxtra_sensor01",
  "flow": 12.5,
  "total": 1234.56,
  "level": 2.3,
  "ts": 1674234567
}
```

**Parsing Rule:**
```python
parsing_method: "template"
field_mappings: {
  "flow": "payload.{flow}",
  "total": "payload.{total}",
  "nivel": "payload.{level}"
}
```

---

### 3. Binario/Hex (Novus típico)

```
Payload (bytes): 0x12 0x34 0x56 0x78 0xAB 0xCD
```

**Parsing Rule:**
```python
parsing_method: "python"
field_mappings: {
  "pulses": "struct.unpack('>I', payload[0:4])[0]",
  "timestamp": "struct.unpack('>I', payload[4:8])[0]"
}
```

---

## 🧪 Testing

### 1. Publicar mensaje de prueba

```bash
# Desde tu máquina
docker exec mqtt_broker_dev mosquitto_pub \
  -h localhost \
  -p 1883 \
  -t "nxtra/sensor01/data" \
  -m '{"device_id":"sensor01","data":{"flow":12.5,"total_m3":1234.56},"timestamp":"2026-01-20T15:30:00"}'
```

### 2. Verificar logs

```bash
docker logs -f smarthydro_django_dev
```

Deberías ver:
```
INFO Mensaje recibido en topic: nxtra/sensor01/data
INFO Telemetría guardada exitosamente para sensor01
```

### 3. Verificar en base de datos

```bash
docker exec smarthydro_django_dev python manage.py shell
```

```python
from api.telemetry.models import TelemetryRecord

# Ver últimos registros
records = TelemetryRecord.objects.order_by('-timestamp')[:5]
for r in records:
    print(f"{r.point.point_code}: {r.data}")
```

---

## 🔥 Ejemplo Completo: NXTRA con Nettra

### Payload que envía NXTRA Nettra:

```json
{
  "deviceId": "nettra_001",
  "timestamp": 1674234567,
  "sensors": {
    "flow_sensor": {
      "value": 12.5,
      "unit": "L/s"
    },
    "pressure_sensor": {
      "value": 2.3,
      "unit": "bar"
    }
  }
}
```

### Configuración en Django:

**1. TelemetryProvider:**
```python
Name: mqtt_nxtra_nettra
Display Name: NXTRA Nettra MQTT
```

**2. MQTTProviderConfig:**
```python
Broker Host: localhost
Broker Port: 1883
Subscribe Topic Template: "nxtra/nettra/{device_id}/sensors"
```

**3. PayloadParsingRule:**
```python
Name: Nettra Sensor Parser
Parsing Method: jsonpath

Field Mappings:
{
  "flow": {
    "source": "$.sensors.flow_sensor.value",
    "type": "jsonpath"
  },
  "presion": {
    "source": "$.sensors.pressure_sensor.value",
    "type": "jsonpath"
  },
  "timestamp": {
    "source": "$.timestamp",
    "type": "jsonpath"
  }
}

Transformations:
[
  {
    "field": "timestamp",
    "type": "unix_to_datetime"
  }
]
```

**4. CatchmentPoint + CatchmentPointMQTT:**
```python
# CatchmentPoint
Point Code: NETTRA_SENSOR_001

# CatchmentPointMQTT
Custom Device ID: nettra_001
Custom Topics: {"subscribe": "nxtra/nettra/nettra_001/sensors"}
```

---

## 🎯 Ventajas de Esta Arquitectura

✅ **100% Configurable desde Admin** - No código hardcodeado
✅ **Multi-Dispositivo** - Soporta NXTRA, Novus, Nettra, etc.
✅ **Parsing Flexible** - JSON, binario, regex, custom
✅ **Validación Automática** - Min/max, tipos, requeridos
✅ **FormulaEngine Integrado** - Cálculos complejos
✅ **Topics Dinámicos** - Templates con variables
✅ **Escalable** - Agrega dispositivos sin código

---

## 🐛 Troubleshooting

### El servicio no recibe mensajes

1. **Verificar broker está corriendo:**
```bash
docker ps | grep mqtt
```

2. **Verificar permisos mosquitto.conf:**
```
allow_anonymous true
```

3. **Test directo con mosquitto_sub:**
```bash
docker exec mqtt_broker_dev mosquitto_sub -h localhost -t "#" -v
```

### Mensajes llegan pero no se guardan

1. **Verificar device_id se extrae correctamente:**
```python
# En mqtt_subscriber_service.py, agregar log
logger.info(f"Device ID extraído: {device_id}")
```

2. **Verificar existe CatchmentPointMQTT:**
```python
from api.telemetry.providers.mqtt_models import CatchmentPointMQTT
CatchmentPointMQTT.objects.filter(is_active=True)
```

3. **Verificar parsing rule aplica:**
```python
# Ver logs de "No hay regla de parsing aplicable"
```

---

## 🚀 Próximos Pasos

1. **Configurar autenticación MQTT** (usuario/password)
2. **Habilitar TLS** para producción
3. **Agregar más reglas de parsing** para diferentes dispositivos
4. **Implementar alertas** cuando dispositivo no envía datos
5. **Dashboard en tiempo real** con WebSockets

---

## 📚 Referencias

- [mqtt_subscriber_service.py](mqtt_subscriber_service.py) - Servicio principal
- [mqtt_models.py](mqtt_models.py) - Modelos de configuración
- [mqtt_parser.py](mqtt_parser.py) - Parser de payloads
- [mosquitto.conf](/conf/mosquitto.conf) - Configuración broker

---

**¿Necesitas ayuda?** Revisa los logs con:
```bash
docker logs -f smarthydro_django_dev | grep MQTT
```
