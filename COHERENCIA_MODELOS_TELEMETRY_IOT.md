# 📊 COHERENCIA: Modelos TELEMETRY vs INFRASTRUCTURE (IoT)

**Fecha:** 2026-01-22
**Problema resuelto:** Tabla `infrastructure_device` faltante - CREADA ✅

---

## 🎯 RESUMEN EJECUTIVO

| App | Propósito | Estado | Registros |
|-----|-----------|--------|-----------|
| **telemetry** | Datos de sensores, processing | ✅ Activo | 1 CatchmentPoint |
| **telemetry.providers** | Ingesta de datos (canales) | ✅ Activo | 5 Providers |
| **infrastructure** | Hardware físico (inventario) | ✅ Activo | 0 devices (listo) |

---

## 📦 1. APP: INFRASTRUCTURE (api.infrastructure)

### Propósito
**Inventario y gestión de HARDWARE FÍSICO**

### Modelos

#### 1.1 Manufacturer (Fabricante)
```
Ejemplos: Novus, Siemens, Campbell Scientific
```
**Campos:**
- name, code, website
- contact_email, contact_phone
- mqtt_broker_host, mqtt_broker_port (configuración MQTT del fabricante)
- integration_status

**Uso:**
- Catálogo de fabricantes de equipos
- Info de contacto para soporte
- Configuración MQTT si el fabricante provee broker

**Estado BD:** ✅ Tabla `infrastructure_manufacturer` existe
**Registros:** 0

---

#### 1.2 DeviceModel (Modelo de Equipo)
```
Ejemplos:
  - Novus NXperience
  - Siemens S7-1200
  - Campbell CR1000
```
**Campos:**
- manufacturer (FK)
- model_name, model_code
- description
- is_active

**Uso:**
- Catálogo de modelos de equipos
- Especificaciones técnicas
- Documentación

**Estado BD:** ✅ Tabla `infrastructure_devicemodel` existe
**Registros:** 0

---

#### 1.3 Device (Equipo Físico)
```
Ejemplos:
  - Sensor Novus NXperience serial NXP-001-2024
  - PLC Siemens serial PLC-789-2023
```
**Campos:**
- device_id (único)
- serial_number
- name
- device_model (FK)
- catchment_point (FK) - PUEDE tener punto asociado
- status (active, maintenance, retired)
- last_seen
- battery_level

**Uso:**
- Inventario de hardware
- Trazabilidad (qué equipo generó cada dato)
- Mantenimiento y garantías
- Historial de fallas

**Estado BD:** ✅ Tabla `infrastructure_device` **CREADA HOY**
**Registros:** 0

---

#### 1.4 Connection (Conexión MQTT Legacy)
```
⚠️  LEGACY - Reemplazado por TelemetryProvider
```
**Campos:**
- connection_name
- broker_host, broker_port
- manufacturer (FK)
- status (CONNECTED, DISCONNECTED)

**Uso:**
- ❌ **NO USAR** - Legacy
- ✅ Usar `TelemetryProvider` con `provider_type='mqtt_server'` o `'mqtt_client'`

**Estado BD:** ✅ Tabla `infrastructure_connection` existe
**Registros:** 0
**Decisión:** Mantener por compatibilidad pero NO usar en código nuevo

---

## 📊 2. APP: TELEMETRY (api.telemetry)

### Propósito
**Datos de sensores, processing, fórmulas, almacenamiento**

### Modelos Clave

#### 2.1 CatchmentPoint (Punto de Captación)
```
Ejemplo: Pozo Norte, Estación Río Maipo
```
**Campos:**
- title, point_code
- owner_user (FK)
- lat, lon
- is_active
- frequency (FK)
- processing_scheme (FK)
- configuration_scheme (FK)

**Relaciones importantes:**
- `devices` (M2M → infrastructure.Device) - Equipos instalados en este punto
- `provider_configs` (FK ← CatchmentPointProvider) - Canales de datos
- `telemetry` (FK ← TelemetryRecord) - Datos históricos

**Uso:**
- Agrupación lógica de equipos
- Punto de reporte a DGA/SMA
- Dashboard de cliente
- Permisos de acceso

**Estado BD:** ✅ Tabla `core_catchmentpoint` existe
**Registros:** 1

---

#### 2.2 TelemetryRecord (Dato Procesado)
```
Almacena los datos finales ya procesados
```
**Campos:**
- point (FK)
- timestamp
- data (JSON) - Variables procesadas
- metadata (JSON)

**Uso:**
- Almacenamiento histórico
- Consultas de datos
- Reportes

**Estado BD:** ✅ Existe
**Registros:** Variable

---

#### 2.3 Otros Modelos Telemetry
- ConfigurationScheme - Esquema de configuración de puntos
- TelemetryScheme - Esquema de procesamiento
- VariableDefinition - Definición de variables
- DataPoint - Datos granulares
- SystemConfiguration - Config global

**Uso:** Processing y configuración avanzada

---

## 📡 3. APP: TELEMETRY.PROVIDERS (api.telemetry.providers)

### Propósito
**Ingesta de datos - CANALES de comunicación**

### Modelos Clave

#### 3.1 TelemetryProvider (Canal de Datos)
```
Ejemplos:
  - API de Nettra
  - Broker MQTT de Novus
  - Broker MQTT Propio
```
**Campos:**
- name, display_name
- provider_type:
  - `'api'`: REST API
  - `'mqtt_server'`: Broker local (equipos publican hacia SmartHydro)
  - `'mqtt_client'`: Broker externo (SmartHydro consume de terceros)
  - `'modbus'`: ModBus TCP
- base_url
- auth_method, auth_config
- endpoint_template

**Uso:**
- Definir CÓMO llegan datos a SmartHydro
- Un provider puede servir datos de múltiples devices
- Failover: 1 device puede usar múltiples providers

**Estado BD:** ✅ Tabla `telemetry_providers_telemetryprovider` existe
**Registros:** 5 (3 API + 2 MQTT)

---

#### 3.2 CatchmentPointProvider (Punto ↔ Provider ↔ Device)
```
TABLA INTERMEDIA que conecta los 3 conceptos
```
**Campos:**
- point (FK → CatchmentPoint) - ¿DÓNDE?
- provider (FK → TelemetryProvider) - ¿CÓMO llegan datos?
- device (FK → Device) - ¿QUÉ equipo físico? ✅ NUEVO
- provider_device_id - ID del device en el sistema del PROVIDER
- priority - Orden de failover (mayor = preferido)
- device_config (JSON) - Config específica del device
- config_override (JSON) - Override de config del provider

**Ejemplo:**
```python
CatchmentPointProvider:
  point = Pozo Norte (CatchmentPoint)
  provider = API Nettra (TelemetryProvider)
  device = Sensor NXP-001-2024 (Device)
  provider_device_id = "station_123"  # Así lo identifica Nettra
  priority = 10
```

**Uso:**
- Relacionar punto lógico con canal de datos
- Saber qué device físico genera los datos (trazabilidad)
- Failover: múltiples providers por punto
- Configuración por device

**Estado BD:** ✅ Tabla `telemetry_providers_catchmentpointprovider` existe
**Registros:** 1

---

#### 3.3 MQTTProviderConfig (Config MQTT)
```
Configuración específica para providers MQTT
```
**Campos:**
- provider (OneToOne)
- service_identifier
- mode:
  - `'server'`: Escuchar broker local
  - `'client'`: Conectar a broker externo
- broker_host, broker_port
- subscribe_topic_template
- publish_topic_template

**Uso:**
- Configurar conexión MQTT
- Definir topics
- Diferenciar cliente vs servidor

**Estado BD:** ✅ Existe
**Registros:** 2

---

#### 3.4 PayloadParsingRule (Reglas de Parsing)
```
Cómo parsear payloads de diferentes formatos
```
**Uso:**
- Extraer campos de JSON/binary/texto
- JSONPath, regex, templates
- Validaciones

**Estado BD:** ✅ Existe
**Registros:** 3

---

#### 3.5 ComplianceProvider (Salida a Gobierno)
```
⚠️  DIFERENTE de TelemetryProvider
```
**Dirección:** SmartHydro → DGA/SMA (SALIDA)

**Uso:**
- Envío de datos a entidades regulatorias
- NO confundir con ingesta (TelemetryProvider)

**Estado BD:** ✅ Existe
**Registros:** 2 (DGA, SMA)

---

## 🔗 COHERENCIA: Cómo se Relacionan

### Flujo Completo: Del Sensor a la DGA

```
1. HARDWARE FÍSICO (infrastructure)
   ├─ Manufacturer: Novus
   ├─ DeviceModel: NXperience
   └─ Device: serial NXP-001-2024
       ├─ status: active
       ├─ battery_level: 85%
       └─ catchment_point: Pozo Norte

2. PUNTO LÓGICO (telemetry)
   └─ CatchmentPoint: Pozo Norte
       ├─ title: "Pozo Norte"
       ├─ owner: Cliente ABC
       └─ devices: [NXP-001-2024, PLC-789-2023]

3. INGESTA (telemetry.providers)
   ├─ TelemetryProvider: API Nettra
   │  ├─ type: api
   │  ├─ base_url: https://api.nettra.cl
   │  └─ auth: Bearer token
   │
   └─ CatchmentPointProvider:
       ├─ point: Pozo Norte
       ├─ provider: API Nettra
       ├─ device: NXP-001-2024 ← Trazabilidad
       ├─ provider_device_id: "station_123" ← ID en Nettra
       └─ priority: 10

4. PROCESAMIENTO (telemetry)
   ├─ TelemetryScheme: Fórmulas
   ├─ FormulaEngine: Cálculos
   └─ TelemetryRecord: Datos guardados

5. SALIDA (telemetry.providers.compliance)
   ├─ ComplianceProvider: DGA
   └─ PointComplianceConfig: Config para enviar a DGA
```

---

## ✅ VENTAJAS DE ESTA ARQUITECTURA

### 1. Separación Clara de Responsabilidades

| Capa | Responsabilidad | Ejemplo |
|------|----------------|---------|
| **infrastructure** | Hardware físico | Sensor NXP-001-2024 |
| **telemetry** | Punto lógico + datos | Pozo Norte |
| **telemetry.providers** | Canales de ingesta | API Nettra |

### 2. Trazabilidad Completa

```
TelemetryRecord ID 12345:
  ├─ point: Pozo Norte
  ├─ timestamp: 2026-01-22 10:30:00
  └─ ¿Qué device generó este dato?
      → Via CatchmentPointProvider
      → device: Sensor NXP-001-2024
      → provider: API Nettra
      → provider_device_id: "station_123"
```

### 3. Failover Automático

```
Pozo Norte:
  └─ Providers (ordenados por priority):
     ├─ [10] API Nettra → device: NXP-001-2024
     │   Status: ✅ Funcionando
     │
     └─ [5] MQTT Directo → device: NXP-001-2024
         Status: 🔄 Backup (usa si API falla)
```

### 4. Inventario de Hardware

```
Django Admin → Infrastructure → Devices
  ├─ NXP-001-2024
  │  ├─ Model: Novus NXperience
  │  ├─ Installed: 2024-01-15
  │  ├─ Location: Pozo Norte
  │  ├─ Warranty: Hasta 2026-01-10
  │  ├─ Status: Active
  │  └─ Battery: 85%
  │
  └─ PLC-789-2023
     ├─ Model: Siemens S7-1200
     ├─ Status: Active
     └─ ...
```

### 5. Reemplazo de Equipos Sin Perder Config

```
Sensor NXP-001-2024 se rompe.
Instalas NXP-002-2024.

Cambios necesarios:
  1. Device NXP-001-2024: status = "retired"
  2. Device NXP-002-2024: status = "active"
  3. CatchmentPointProvider:
     - device: NXP-001-2024 → NXP-002-2024
     - provider_device_id: puede cambiar o no

✅ Config del provider: sin cambios
✅ Config del punto: sin cambios
✅ Historial: ambos devices preservados
```

---

## 📋 GUÍA DE USO

### Caso 1: Agregar Nuevo Sensor

```python
# 1. Crear Device físico
device = Device.objects.create(
    device_id='NXP-003-2026',
    serial_number='NXP-003-2026',
    name='Sensor Caudal Novus',
    device_model=nxperience_model,
    status='active'
)

# 2. Relacionar con CatchmentPoint
punto.devices.add(device)

# 3. Configurar ingesta via Provider
CatchmentPointProvider.objects.create(
    point=punto,
    provider=nettra_api,
    device=device,
    provider_device_id='station_456',  # ID en Nettra
    priority=10
)
```

### Caso 2: Consultar Qué Device Generó un Dato

```python
# Tengo un TelemetryRecord
record = TelemetryRecord.objects.get(id=12345)

# ¿Qué device lo generó?
cpp = CatchmentPointProvider.objects.filter(
    point=record.point,
    is_active=True
).select_related('device').first()

if cpp and cpp.device:
    print(f"Generado por: {cpp.device.serial_number}")
    print(f"Modelo: {cpp.device.device_model.model_name}")
    print(f"Vía provider: {cpp.provider.display_name}")
```

### Caso 3: Mantenimiento - Listar Equipos por Estado

```python
# Equipos activos
active = Device.objects.filter(status='active')

# Equipos con batería baja
low_battery = Device.objects.filter(
    battery_level__lt=20,
    status='active'
)

# Equipos que no han reportado en 24h
from datetime import timedelta
from django.utils import timezone
stale = Device.objects.filter(
    last_seen__lt=timezone.now() - timedelta(hours=24),
    status='active'
)
```

---

## 🎯 DECISIONES FINALES

### ✅ MANTENER infrastructure

**Razones:**
1. Inventario de hardware es DIFERENTE de canales de ingesta
2. Necesario para trazabilidad
3. Gestión de mantenimiento
4. Sin datos pero LISTO para usar

**Status:**
- ✅ Modelos definidos
- ✅ Migraciones aplicadas
- ✅ Tabla `infrastructure_device` **CREADA HOY**
- ✅ Admin configurado
- ⏳ 0 registros (esperando uso)

### ❌ NO USAR infrastructure.Connection

**Razón:** Legacy, reemplazado por TelemetryProvider

**Migración:**
- Viejo: Connection con broker MQTT
- Nuevo: TelemetryProvider con `provider_type='mqtt_server'` o `'mqtt_client'`

---

## 📊 ESTADO ACTUAL DEL SISTEMA

| Componente | Tabla BD | Registros | Admin | Estado |
|------------|----------|-----------|-------|--------|
| **Manufacturer** | ✅ infrastructure_manufacturer | 0 | ✅ | Listo |
| **DeviceModel** | ✅ infrastructure_devicemodel | 0 | ✅ | Listo |
| **Device** | ✅ infrastructure_device | 0 | ✅ | **Creado hoy** |
| **Connection** | ✅ infrastructure_connection | 0 | ✅ | Legacy (no usar) |
| **CatchmentPoint** | ✅ core_catchmentpoint | 1 | ✅ | Activo |
| **TelemetryProvider** | ✅ telemetry_providers_telemetryprovider | 5 | ✅ | Activo |
| **CatchmentPointProvider** | ✅ telemetry_providers_catchmentpointprovider | 1 | ✅ | Activo |
| **MQTTProviderConfig** | ✅ telemetry_providers_mqttproviderconfig | 2 | ✅ | Activo |

---

## ✅ CONCLUSIÓN

La arquitectura es **COHERENTE** con 3 capas claras:

1. **infrastructure** → Hardware físico (Device, DeviceModel, Manufacturer)
2. **telemetry** → Punto lógico + datos (CatchmentPoint, TelemetryRecord)
3. **telemetry.providers** → Canales de ingesta (TelemetryProvider, CatchmentPointProvider)

**Problema resuelto hoy:**
- ✅ Tabla `infrastructure_device` faltante → **CREADA**
- ✅ Admin funcional
- ✅ Relaciones FK correctas
- ✅ Listo para usar

**Siguiente paso:**
Crear tus primeros Manufacturers, DeviceModels y Devices para empezar a trackear hardware.
