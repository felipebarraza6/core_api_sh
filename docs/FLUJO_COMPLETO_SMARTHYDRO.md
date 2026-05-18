# Flujo Completo SmartHydro — Guía Didáctica

> **Versión:** 2026-05-17  
> **Para:** Entender cómo funciona todo desde que configuras un punto hasta que los datos llegan, se procesan, alertan y se envían a reguladores.

---

## 🎯 El escenario

Vas a configurar un **nuevo punto de captación** llamado "Pozo Norte" en un proyecto llamado "Minera Los Andes".

El pozo tiene:
- Un sensor de caudal (L/s)
- Un sensor de nivel (metros)
- Un contador totalizado (m³ acumulados)
- Debe enviar datos a **DGA** (cada 3 minutos)
- Debe enviar datos a **SMA** (cada 5 minutos)
- Frecuencia de telemetría: cada 5 minutos

---

## PASO 1: Crear el punto (`CatchmentPoint`)

**Vas al admin Django → Puntos de Captación → Agregar.**

**Qué completás:**
- **Título:** "Pozo Norte"
- **Proyecto:** "Minera Los Andes"
- **Frecuencia:** 5 minutos
- **Usuario propietario:** El cliente

**Qué pasa internamente:**
Se crea un registro en la tabla `core_catchmentpoint` con:
- `title = "Pozo Norte"`
- `frecuency = "5"`
- `project_id = X`
- `owner_user_id = Y`
- `is_tdata = False` (legacy)
- `is_thethings = False` (legacy)
- `is_novus = False` (legacy)
- `telemetry_provider = NULL` (todavía no lo asignaste)

**⚠️ Hardcodeado aquí:** Solo podés elegir frecuencias 1, 5, 10 o 60 minutos. No existe 15 ni 30.

---

## PASO 2: Configurar telemetría (`ProfileDataConfigCatchment`)

**Vas al admin → Configuración de Datos → Agregar.**

**Qué completás:**
- **Punto:** "Pozo Norte" (el que acabás de crear)
- **¿Es telemetría?** Sí (`is_telemetry = True`)
- **Token del servicio:** El token que te dio TwinDimension (ej: `"abc123"`)
- **Posicionamiento nivel (d3):** 45.5 metros
- **Nivel offset:** -2.0 (si el sensor mide 2m por encima del nivel real)
- **Replicar datos faltantes:** Sí (si un cron falla, copia el último valor)

**Qué son esos campos raros d1-d6:**

| Campo | Qué es | Ejemplo |
|-------|--------|---------|
| `d1` | Profundidad de bomba | 120 mt |
| `d2` | Posición de bomba | 80 mt |
| `d3` | Posición del sensor de nivel | 45.5 mt |
| `d4` | Diámetro ducto salida | 6 pulg |
| `d5` | Diámetro flujómetro | 4 pulg |
| `d6` | Caudalímetro inicial | 0 |

**⚠️ Problema:** Estos nombres (`d1`, `d2`, etc.) están fijos en el código. Si querés agregar "Profundidad del pozo" o "Temperatura del agua", no podés. Tenés que reusar `d1`-`d6` con nombres que no corresponden.

**Qué pasa internamente:**
Se crea un registro en `core_profiledataconfigcatchment` vinculado al punto.

---

## PASO 3: Configurar el esquema y variables (`SchemesCatchment` → `Variable`)

**Vas al admin → Esquemas → Agregar.**

**Creás un esquema** "Esquema Pozo Estándar" con 3 variables:

| Variable | Código proveedor | Tipo | display_key | min | max |
|----------|-----------------|------|-------------|-----|-----|
| Caudal Instantáneo | `5001` | CAUDAL | `caudal` | 0 | 1000 |
| Nivel Piezométrico | `5002` | NIVEL | `nivel` | -200 | 200 |
| Volumen Acumulado | `5003` | TOTALIZADO | `total` | 0 | null |

**Qué significa cada campo:**
- **str_variable:** El código que usa el proveedor (TwinDimension, Novus, etc.)
- **type_variable:** Qué representa (CAUDAL, NIVEL, TOTALIZADO, CAUDAL_PROMEDIO)
- **display_key:** Cómo se muestra en el frontend Ikolu (`caudal`, `nivel`, `total`)
- **min/max:** Rango válido. Si el sensor manda -5 L/s, el sistema marca `is_error=True`
- **pulses_factor:** Si el sensor manda "pulsos", se multiplica por esto. Default: 1000

**⚠️ Hardcodeado:** Solo existen 4 tipos de variable. No podés crear "TEMPERATURA" o "pH".

**Asociás el esquema al punto** "Pozo Norte".

---

## PASO 4: Configurar el proveedor de telemetría (`TelemetryProvider`)

**Vas al admin → Proveedores de Telemetría.**

**Elegís:** "TwinDimension" (handler_name = `tdata`)

**El sistema usa este proveedor para:**
1. Saber a qué URL pedir los datos
2. Cómo autenticarse (token JWT)
3. Cómo leer la respuesta JSON

**Internamente:**
El cronjob `telemetry_unified.py` filtra puntos así:
```
puntos = CatchmentPoint.objects.filter(
    telemetry_provider__handler_name = "tdata"
)
```

También funciona con el booleano legacy `is_tdata=True`, pero eso es viejo.

---

## PASO 5: Configurar cumplimiento DGA (`DgaDataConfigCatchment`)

**Vas al admin → Configuración DGA → Agregar.**

**Completás:**
- **Punto:** "Pozo Norte"
- **¿Enviar a DGA?** Sí (`send_dga = True`)
- **Estándar:** MAYOR (cada hora envía el caudal promedio)
- **Tipo:** SUBTERRANEO
- **Código de obra:** OB-1234-56
- **Caudal otorgado:** 50.00 L/s
- **RUT informante:** 12345678-9 (⚠️ si no lo cambiás, queda 17352192-8 por defecto)
- **Contraseña DGA:** (si no la ponés, usa la del sistema)

**⚠️ Hardcodeado:** El nombre del informante default es "Diego Mardones" y el RUT default es "17352192-8". Si te olvidás de cambiarlos, los envíos van con esos datos.

---

## PASO 6: Configurar cumplimiento SMA (`DgaDataConfigCatchment`)

**En la misma pantalla de DGA**, ahora también completás:
- **¿Enviar a SMA?** Sí (`send_sma = True`) ✅ *Nuevo campo*
- **ID dispositivo SMA:** 12180 (o el que te dieron) ✅ *Nuevo campo*

**Antes** esto no se podía configurar — solo el punto 1 enviaba a SMA con ID 12180 fijo.

---

## PASO 7: Empiezan a llegar datos (cronjob cada 5 min)

### 7.1 El cronjob despierta
Cada 5 minutos corre `telemetry_unified.py`:
```bash
python manage.py crontab run [hash] >> /tmp/smarthydro/unified_twin_5.log
```

### 7.2 ¿Qué puntos procesa?
Busca puntos con:
- `frecuency = "5"`
- `is_telemetry = True`
- `telemetry_provider__handler_name = "tdata"` (o `is_tdata = True` como fallback)

"Pozo Norte" aparece en la lista.

### 7.3 Pide datos al proveedor
Por cada variable del esquema:

**Variable "Caudal Instantáneo" (str_variable = "5001"):**
1. Llama a la API de TwinDimension:
   ```
   GET /telemetry/DEVICE/abc123/values/timeseries?keys=5001
   ```
2. Recibe respuesta:
   ```json
   {"date_time": "2026-05-17T14:05:00", "value": 42.5}
   ```

**Variable "Nivel" (str_variable = "5002"):**
- Similar, pero pide `keys=5002`

**Variable "Totalizado" (str_variable = "5003"):**
- Similar, pero pide `keys=5003`

### 7.4 Procesa cada variable

#### TOTALIZADO (el primero, siempre)
1. **Convierte pulsos a m³:**
   ```
   pulsos = 42500
   factor = 1000
   total_m3 = (42500 * 1000) / 1000 = 42500 m³
   ```

2. **Detecta resets:**
   - Último valor anterior: 42499
   - Si el sensor se reseteó (vuelve a 0), calcula un `addition` y lo guarda en `ProfileDataConfigCatchment.addition`

3. **Anti-salto masivo:**
   - Si la diferencia entre este valor y el anterior es > 500 m³/h, lo ignora y mantiene el último válido
   - ⚠️ **Ese 500 está hardcodeado.** Un pozo grande podría consumir más.

4. **Calcula diffs:**
   - `total_diff` = diferencia con el registro anterior (consumo en la última hora)
   - `total_today_diff` = diferencia con el primer registro del día

#### NIVEL
1. Aplica `nivel_offset` (ej: -2.0)
2. Si el valor es negativo, busca el nivel más alto histórico como fallback
3. Calcula `water_table` = `d3` - `nivel`
   - Ej: 45.5 - 12.3 = 33.2 metros

#### CAUDAL
1. Convierte el valor crudo a L/s según el sensor
2. Si `convert_to_lt = True`, divide por 3.6
3. Si el valor > 150 L/s, lo pone en 0
   - ⚠️ **Ese 150 está hardcodeado.** Una bomba grande puede dar más.

### 7.5 Valida rangos (lo nuevo)
Antes de guardar, revisa `min_value` y `max_value`:

- Si caudal = -5.0 y `min_value = 0` → ❌ **Marca `is_error = True`**
- Si nivel = 250.0 y `max_value = 200` → ❌ **Marca `is_error = True`**

**El registro se guarda igual**, pero queda marcado como error para alertas y reportes.

### 7.6 Guarda el registro
```python
InteractionDetail.objects.create(
    catchment_point = "Pozo Norte",
    date_time_medition = "2026-05-17T14:05:00",
    flow = 42.5,           # ← legacy
    nivel = 12.3,          # ← legacy
    total = 42500,         # ← legacy
    water_table = 33.2,    # ← legacy
    is_error = False,
    variable_values = {     # ← NUEVO
        "101": 42.5,        # variable_id 101 = caudal
        "102": 12.3,        # variable_id 102 = nivel
        "103": 42500        # variable_id 103 = total
    }
)
```

**Los campos `flow`, `nivel`, `total` siguen existiendo** para no romper el frontend legacy.
**`variable_values` es el futuro** — permite tener 50 variables sin tocar la BD.

---

## PASO 8: Cumplimiento DGA (cada 3 minutos)

### 8.1 El cronjob `cron_dga.py` despierta
Busca registros con `send_dga = True` que aún no se enviaron.

### 8.2 Prepara el payload
Para cada registro de "Pozo Norte":

1. **Caudal:**
   - Si estándar es MAYOR → calcula promedio de la última hora
   - Si no → usa el caudal instantáneo

2. **Total:**
   - Toma `register.total`
   - Le resta `ProfileDataConfigCatchment.addition` (el reset del sensor)
   - DGA recibe el total "real", no el crudo del sensor

3. **Construye JSON:**
   ```json
   {
     "medicionSubterranea": {
       "codigoObra": "OB-1234-56",
       "fecha": "2026-05-17T14:00:00",
       "caudal": 42.5,
       "nivel": 12.3,
       "total": 42500
     }
   }
   ```

4. **Autentica:**
   - Obtiene token OAuth2 de DGA
   - Usa `rut_report_dga` y `password_dga_software` del punto

5. **Envía:**
   ```
   POST https://apimee.mop.gob.cl/api/v1/mediciones/subterraneas
   ```

6. **Recibe comprobante:**
   - Si todo OK → DGA devuelve un número de comprobante único
   - El sistema guarda ese comprobante en `n_voucher`

**⚠️ Lógica hardcodeada:**
- Si el punto fuera el 83, el sistema automáticamente suma los totales de los puntos 84 y 85. Esto es lógica de un cliente específico, hardcodeada en el código de DGA.

---

## PASO 9: Cumplimiento SMA (cada 5 minutos)

### 9.1 El cronjob `cron_sma.py` despierta
Busca puntos con `send_sma = True` (antes solo era el punto 1).

### 9.2 Filtra registros
- Solo registros de los últimos 2 horas
- Solo minutos múltiplos de 5 (0, 5, 10, 15...)
- Solo registros sin `n_voucher` (no enviados aún)

### 9.3 Prepara payload
```json
[{
  "dispositivoId": "12180",
  "parametros": [
    {"nombre": "Q", "valor": "42.5", "unidad": "l/s", "estampaTiempo": "2026-05-17T14:05:00"},
    {"nombre": "VA", "valor": "42500", "unidad": "m3", "estampaTiempo": "2026-05-17T14:05:00"}
  ]
}]
```

**Antes:** `dispositivoId` siempre era `"12180"` para todos los puntos.
**Ahora:** Lee de `DgaDataConfigCatchment.sma_device_id`, configurable por punto.

### 9.4 Envía
```
POST https://conexiones.sma.gob.cl/api/v1/ufs/7511/procesos/5368/registros
Authorization: Bearer [token]
```

---

## PASO 10: Alertas (cada minuto)

### 10.1 El motor `alert_engine.py` despierte
Cada minuto evalúa reglas activas.

### 10.2 ¿Qué reglas evalúa?
Solo las cuya frecuencia coincida con el minuto actual:
- Si la regla tiene `check_frequency_minutes = 5` → se evalúa en minutos 0, 5, 10, 15...
- Si tiene `check_frequency_minutes = 10` → minutos 0, 10, 20...

### 10.3 Tipos de alerta

**THRESHOLD_MAX (ej: caudal > 50 L/s):**
1. Lee el último `InteractionDetail` del punto
2. Extrae el caudal
3. Si es > 50 → crea un `AlertTrigger`

**DISCONNECTION (punto sin datos):**
1. Lee `days_not_conection` del último registro
2. Si es > 0 → el punto está desconectado
3. Si lleva más de 3 días desconectado → **lo ignora** (para no spammear)
   - ⚠️ Ese "3 días" está hardcodeado como default

**RECONNECTION:**
1. Compara los últimos 2 registros
2. Si el anterior tenía `days_not_conection > 0` y el actual tiene `0` → se reconectó

**PROCESSING_ERROR:**
1. Busca registros con `is_error = True` en los últimos 10 minutos
2. Si encuentra alguno → dispara alerta

### 10.4 El dispatcher envía notificaciones
Cuando se crea un `AlertTrigger`, el `alert_dispatcher.py`:
1. Obtiene los canales configurados (Google Chat, Email, Webhook)
2. Si es una desconexión → **genera diagnóstico con IA** (Gemini)
3. Envía el mensaje:
   ```
   🚨 ALERTA: Desconexión de puntos
   📍 Punto: Pozo Norte
   🏢 Cliente: Minera Los Andes
   📊 Días sin conexión: 2
   🤖 Diagnóstico IA: Posible fallo de batería del logger...
   📌 Asignado a: @andresnunez@smarthydro
   ```

---

## PASO 11: El frontend Ikolu lee los datos

### 11.1 Dashboard de puntos
```
GET /api/ik/points_summary/
```
Devuelve:
```json
{
  "points": [{
    "id": 999,
    "title": "Pozo Norte",
    "provider": "tdata",
    "latest_telemetry": {
      "flow": "42.50",
      "nivel": "12.30",
      "total": "42500",
      "is_error": false,
      "variable_values": {
        "101": 42.5,
        "102": 12.3,
        "103": 42500
      }
    }
  }]
}
```

### 11.2 Detalle de variables
```
GET /api/ik/point/999/variables/
```
Devuelve:
```json
{
  "variables": [
    {"id": 101, "display_key": "caudal", "min_value": "0.0000", "max_value": "1000.0000"},
    {"id": 102, "display_key": "nivel", "min_value": "-200.0000", "max_value": "200.0000"},
    {"id": 103, "display_key": "total", "min_value": "0.0000", "max_value": null}
  ],
  "mapping": {
    "101": "caudal",
    "102": "nivel",
    "103": "total"
  }
}
```

El frontend usa `mapping` para saber que `variable_values["101"]` es el caudal.

---

## 🗺️ Mapa visual del flujo completo

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CONFIGURACIÓN (Admin Django)                                           │
│                                                                         │
│  CatchmentPoint ──► ProfileDataConfigCatchment (telemetría)            │
│       │                    │                                            │
│       │                    ├── d1-d6 (configurables, nombres fijos)    │
│       │                    ├── token_service                            │
│       │                    ├── nivel_offset                             │
│       │                    └── addition (reset acumulado)               │
│       │                                                                 │
│       ├──► SchemesCatchment ──► Variable (x N)                          │
│       │       │              ├── str_variable (código proveedor)        │
│       │       │              ├── type_variable (CAUDAL/NIVEL/TOTAL)     │
│       │       │              ├── display_key (caudal/nivel/total) ✅    │
│       │       │              ├── min/max (validación) ✅                │
│       │       │              └── provider (FK a TelemetryProvider)      │
│       │                                                                 │
│       ├──► DgaDataConfigCatchment (cumplimiento)                        │
│       │       ├── send_dga, code_dga, standard, type_dga               │
│       │       ├── rut_report_dga (default hardcodeado 17352192-8)      │
│       │       ├── name_informant (default hardcodeado Diego Mardones)  │
│       │       ├── send_sma ✅ (nuevo, configurable)                     │
│       │       └── sma_device_id ✅ (nuevo, configurable)                │
│       │                                                                 │
│       └──► TelemetryProvider (proveedor)                                │
│               ├── handler_name: tdata / thethings / tago                │
│               ├── base_url, endpoint_template                           │
│               └── auth_type, auth_token                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  INGESTA (cada 1/5/10/60 min) — telemetry_unified.py                    │
│                                                                         │
│  1. Filtra puntos por frecuencia + is_telemetry=True                   │
│  2. Por cada punto, por cada variable:                                 │
│     a. get_data_universal() → pide dato al proveedor                   │
│     b. _validate_variable_range() → valida min/max ✅                  │
│     c. process_variable_safely() → procesa según tipo                  │
│        - TOTALIZADO → total_m3() + anti-salto 500 m³/h ⚠️             │
│        - NIVEL → nivel_mt() + water_table()                            │
│        - CAUDAL → instantaneous_flow() + límite 150 L/s ⚠️            │
│     d. Guarda en InteractionDetail:                                     │
│        - flow/nivel/total (legacy)                                     │
│        - variable_values[variable_id] = valor_crudo ✅                 │
│        - is_error=True si falló validación ✅                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CUMPLIMIENTO DGA (cada 3 min) — cron_dga.py                           │
│                                                                         │
│  1. Busca registros con send_dga=True                                  │
│  2. Prepara payload:                                                   │
│     - total SIN offset (resta addition)                                │
│     - caudal según estándar (MAYOR/MEDIO/MENOR)                        │
│  3. Envía a DGA → recibe comprobante                                   │
│  ⚠️ Punto 83 suma automático 84+85 (hardcodeado)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CUMPLIMIENTO SMA (cada 5 min) — cron_sma.py ✅                        │
│                                                                         │
│  1. Busca puntos con send_sma=True (antes solo punto 1) ✅             │
│  2. Filtra minutos múltiplos de 5                                      │
│  3. Prepara payload con dispositivoId configurable ✅                  │
│  4. Envía Q (caudal) + VA (volumen)                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ALERTAS (cada minuto) — alert_engine.py + alert_dispatcher.py          │
│                                                                         │
│  Motor evalúa según frecuencia:                                        │
│  - THRESHOLD_MAX/MIN → valor vs umbral                                 │
│  - DISCONNECTION → days_not_conection > 0                              │
│  - RECONNECTION → transición desconectado→conectado                    │
│  - PROCESSING_ERROR → is_error=True reciente                           │
│                                                                         │
│  Dispatcher:                                                           │
│  - Genera diagnóstico IA (Gemini) para desconexiones                   │
│  - Envía por Google Chat / Email / Webhook                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FRONTEND IKOLU (/api/ik/)                                              │
│                                                                         │
│  points_summary → variable_values + mapping display_key ✅             │
│  point/{id}/variables → lista variables con min/max ✅                 │
│  batch/telemetry → lectura batch últimas N horas                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📋 Resumen: Qué es configurable vs qué es hardcodeado

| Etapa | Configurable | Hardcodeado |
|-------|-------------|-------------|
| **Punto** | Título, proyecto, frecuencia, owner | Frecuencias solo 1/5/10/60 |
| **Telemetría** | Token, offset, addition, replicate | Nombres d1-d6 fijos |
| **Variables** | Código, tipo, display_key, min/max, factor | Solo 4 tipos de variable |
| **Proveedor** | URL, auth, parser, handler | - |
| **DGA** | Código obra, estándar, RUT, password | Defaults nombre/RUT, punto 83 |
| **SMA** | ✅ send_sma, ✅ sma_device_id (nuevo) | Antes: solo punto 1, ID 12180 |
| **Procesamiento** | - | MAX_FLOW=150, MAX_DIFF=500, MAX_GAP=2h |
| **Alertas** | Umbral, frecuencia, canales | max_disconnection_days=3 default |

---

**¿Quedó claro el flujo completo? ¿Hay alguna parte que quieras que profundice?**
