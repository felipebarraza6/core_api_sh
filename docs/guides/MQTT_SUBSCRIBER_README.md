# 🎯 MQTT Subscriber - Resumen Ejecutivo

## ✅ PROBLEMA RESUELTO

Tu pregunta era: **"¿Cómo conectar dispositivos NXTRA/Novus que publican a MI broker MQTT?"**

**Respuesta:** Tu sistema **SÍ está preparado** y ahora tiene una solución completa.

---

## 📦 Lo Que Se Implementó

### 1. **MQTT Subscriber Service**
[`api/telemetry/providers/mqtt_subscriber_service.py`](api/telemetry/providers/mqtt_subscriber_service.py)

Servicio que **escucha tu broker local** y procesa mensajes de dispositivos IoT.

**Características:**
- ✅ Escucha topics dinámicos configurables
- ✅ Parsing flexible (JSON, binario, regex, Python custom)
- ✅ Validación automática de datos
- ✅ Integración con FormulaEngine
- ✅ Soporte multi-dispositivo
- ✅ Cache de configuraciones

---

### 2. **Comando de Gestión**
[`api/telemetry/management/commands/mqtt_subscriber.py`](api/telemetry/management/commands/mqtt_subscriber.py)

```bash
# Iniciar servicio
docker exec smarthydro_django_dev python manage.py mqtt_subscriber start

# Ver estado
docker exec smarthydro_django_dev python manage.py mqtt_subscriber status

# Detener
docker exec smarthydro_django_dev python manage.py mqtt_subscriber stop
```

---

### 3. **Script de Testing**
[`scripts/testing/test_mqtt_subscriber.py`](scripts/testing/test_mqtt_subscriber.py)

```bash
# Enviar un mensaje NXTRA
python scripts/testing/test_mqtt_subscriber.py --type nxtra

# Simular envío continuo Novus
python scripts/testing/test_mqtt_subscriber.py --type novus --simulate --count 20

# Simular todos los tipos
python scripts/testing/test_mqtt_subscriber.py --type all --simulate
```

---

### 4. **Guía Completa**
[`api/telemetry/GUIA_MQTT_SUBSCRIBER.md`](api/telemetry/GUIA_MQTT_SUBSCRIBER.md)

Documentación paso a paso con ejemplos de configuración.

---

## 🎯 Arquitectura

```
┌─────────────────────────────────────────┐
│      Dispositivos IoT (Publican)       │
│   NXTRA │ Novus │ Nettra │ Custom      │
└────────┬────────────────────────────────┘
         │ MQTT PUBLISH
         ↓
┌─────────────────────────────────────────┐
│   Mosquitto Broker (localhost:1883)    │
│   Ya corriendo en tu Docker             │
└────────┬────────────────────────────────┘
         │ MQTT SUBSCRIBE
         ↓
┌─────────────────────────────────────────┐
│   MQTT Subscriber Service (NUEVO)      │
│   - Escucha topics                      │
│   - Parsea payloads                     │
│   - Valida datos                        │
│   - Procesa con FormulaEngine           │
└────────┬────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│   TelemetryRecord (Base de Datos)      │
└─────────────────────────────────────────┘
```

---

## 🚀 Quick Start - 3 Pasos

### Paso 1: Configurar Proveedor en Admin

```python
# Django Admin → TelemetryProvider
Name: mqtt_nxtra
Type: mqtt

# Crear MQTTProviderConfig
Broker Host: localhost
Broker Port: 1883
Subscribe Topic Template: "nxtra/{device_id}/data"
```

### Paso 2: Crear Regla de Parsing

```python
# Django Admin → PayloadParsingRule
Provider: mqtt_nxtra
Name: NXTRA JSON Parser
Parsing Method: jsonpath

Field Mappings:
{
  "flow": {"source": "$.data.flow", "type": "jsonpath"},
  "total": {"source": "$.data.total_m3", "type": "jsonpath"},
  "nivel": {"source": "$.data.water_level", "type": "jsonpath"}
}
```

### Paso 3: Configurar Punto

```python
# Django Admin → CatchmentPointMQTT
Point: [Tu punto de captación]
Provider: mqtt_nxtra
Custom Device ID: sensor01
Is Active: ✅
```

---

## 🧪 Testing

### 1. Iniciar Servicio

```bash
docker exec -it smarthydro_django_dev python manage.py mqtt_subscriber start
```

### 2. Enviar Mensaje de Prueba

En otra terminal:

```bash
# Publicar mensaje NXTRA
docker exec mqtt_broker_dev mosquitto_pub \
  -h localhost \
  -t "nxtra/sensor01/data" \
  -m '{"device_id":"sensor01","data":{"flow":12.5,"total_m3":1234.56,"water_level":2.3},"timestamp":"2026-01-20T15:30:00"}'
```

### 3. Ver Logs

```bash
docker logs -f smarthydro_django_dev | grep MQTT
```

Deberías ver:
```
INFO Mensaje recibido en topic: nxtra/sensor01/data
INFO Telemetría guardada exitosamente para sensor01
```

---

## 📝 Formatos de Payload Soportados

### NXTRA JSON
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

### Novus JSON
```json
{
  "deviceId": "novus_sensor02",
  "timestamp": 1674234567,
  "values": {
    "pulses": 123456,
    "temperature": 25.3
  }
}
```

### NXTRA Nettra Custom
```json
{
  "deviceId": "nettra_001",
  "timestamp": 1674234567,
  "sensors": {
    "flow_sensor": {"value": 15.2, "unit": "L/s"},
    "pressure_sensor": {"value": 2.5, "unit": "bar"}
  }
}
```

---

## 🎯 Diferencias Clave

### ANTES (mqtt_handler.py - Cliente)
```python
# Django SE CONECTA a broker externo
client.connect("broker.external.com", 1883)
client.subscribe("external/+/data")
```
**Uso:** Obtener datos de servicios cloud (AWS IoT, Azure IoT, etc.)

### AHORA (mqtt_subscriber_service.py - Servidor)
```python
# Django ESCUCHA broker local
client.connect("localhost", 1883)
client.subscribe("nxtra/+/data")
```
**Uso:** Recibir datos de dispositivos que se conectan a TI

---

## 💡 Ventajas

✅ **100% Configurable desde Admin** - Sin código hardcodeado
✅ **Multi-Dispositivo** - NXTRA, Novus, Nettra, custom
✅ **Parsing Flexible** - JSON, binario, regex, Python
✅ **Validación Automática** - Min/max, tipos, requeridos
✅ **FormulaEngine Integrado** - Cálculos complejos
✅ **Topics Dinámicos** - Templates con variables
✅ **Escalable** - Agrega dispositivos sin código
✅ **Sistema Existente** - Usa tu broker Mosquitto actual

---

## 📚 Documentación

- **Guía Completa:** [`GUIA_MQTT_SUBSCRIBER.md`](api/telemetry/GUIA_MQTT_SUBSCRIBER.md)
- **Código Fuente:** [`mqtt_subscriber_service.py`](api/telemetry/providers/mqtt_subscriber_service.py)
- **Testing:** [`test_mqtt_subscriber.py`](scripts/testing/test_mqtt_subscriber.py)

---

## 🔥 Ejemplo Real: NXTRA Nettra

### 1. Configuración en Admin

```python
# TelemetryProvider
Name: mqtt_nxtra_nettra
Type: mqtt

# MQTTProviderConfig
Broker Host: localhost
Subscribe Topic: "nxtra/nettra/{device_id}/sensors"

# PayloadParsingRule
Field Mappings:
{
  "flow": {"source": "$.sensors.flow_sensor.value", "type": "jsonpath"},
  "presion": {"source": "$.sensors.pressure_sensor.value", "type": "jsonpath"}
}

# CatchmentPointMQTT
Custom Device ID: nettra_001
```

### 2. Dispositivo Publica

```json
Topic: nxtra/nettra/nettra_001/sensors
Payload: {
  "deviceId": "nettra_001",
  "sensors": {
    "flow_sensor": {"value": 15.2, "unit": "L/s"},
    "pressure_sensor": {"value": 2.5, "unit": "bar"}
  }
}
```

### 3. Django Procesa

```
✅ Topic match: nxtra/nettra/nettra_001/sensors
✅ Device ID: nettra_001
✅ Parsing rule: Nettra Sensor Parser
✅ Extraído: flow=15.2, presion=2.5
✅ Validado: Dentro de rangos
✅ FormulaEngine: Aplicadas fórmulas
✅ Guardado: TelemetryRecord
```

---

## 🎊 Conclusión

**Tu sistema AHORA puede:**
1. ✅ Recibir datos de dispositivos que se conectan a tu broker
2. ✅ Procesar múltiples formatos de payload
3. ✅ Configurar parsing dinámico desde Admin
4. ✅ Validar y almacenar datos automáticamente
5. ✅ Escalar sin modificar código

**Sin necesidad de URL externa**, porque **TÚ eres el servidor** al que los dispositivos se conectan.

---

## 🚀 Siguiente Paso

```bash
# 1. Iniciar el servicio
docker exec -it smarthydro_django_dev python manage.py mqtt_subscriber start

# 2. Configurar tu primer dispositivo en Admin
# 3. Hacer que tu dispositivo publique a: nxtra/{device_id}/data
# 4. Ver la magia ✨
```

**¿Preguntas?** Todo está documentado en [`GUIA_MQTT_SUBSCRIBER.md`](api/telemetry/GUIA_MQTT_SUBSCRIBER.md)
