# 🎯 Flujo Completo en Django Admin - Sistema de Compliance

## 📊 Diagrama de Arquitectura

```
┌──────────────────────────────────────────────────────────────────┐
│                      DJANGO ADMIN                                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1️⃣  CONFIGURAR PROVEEDORES (Una sola vez)                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ ComplianceProvider                                        │   │
│  │ ┌────────────┬────────────┬────────────┬────────────┐    │   │
│  │ │    DGA     │    SMA     │    INDH    │   Custom   │    │   │
│  │ └────────────┴────────────┴────────────┴────────────┘    │   │
│  │                                                            │   │
│  │ Cada uno define:                                          │   │
│  │ • URL API                                                 │   │
│  │ • Método autenticación                                    │   │
│  │ • Template de payload                                     │   │
│  │ • Frecuencia de envío                                     │   │
│  │ • Campos requeridos                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                               │                                   │
│                               ↓                                   │
│  2️⃣  CONFIGURAR PUNTOS                                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ CatchmentPoint: Pozo ABC                                  │   │
│  │                                                            │   │
│  │ Compliance Configurations (Inline):                       │   │
│  │ ┌────────────────────────────────────────────────────┐   │   │
│  │ │ ☑️ DGA                                             │   │   │
│  │ │   Config: {codigo_obra, rut_informante, ...}      │   │   │
│  │ │   ☑️ Send Compliance  ☑️ Is Active                │   │   │
│  │ ├────────────────────────────────────────────────────┤   │   │
│  │ │ ☑️ SMA                                             │   │   │
│  │ │   Config: {res_id, empresa_rut, ...}              │   │   │
│  │ │   ☑️ Send Compliance  ☑️ Is Active                │   │   │
│  │ └────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                    FLUJO AUTOMÁTICO                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  3️⃣  TELEMETRY RECORD GUARDADO                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ TelemetryRecord                                           │   │
│  │ • Point: Pozo ABC                                         │   │
│  │ • Timestamp: 2026-01-20 15:00:00                          │   │
│  │ • Data: {flow: 12.5, total: 1234, nivel: 2.3}            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                               │                                   │
│                               ↓                                   │
│  4️⃣  CHECK COMPLIANCE CONFIGS                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ point.compliance_configs.filter(                          │   │
│  │     is_active=True,                                       │   │
│  │     send_compliance=True                                  │   │
│  │ )                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                               │                                   │
│                 ┌─────────────┴─────────────┐                    │
│                 ↓                           ↓                    │
│  5️⃣  DGA CONFIG               6️⃣  SMA CONFIG                     │
│  ┌─────────────────┐         ┌─────────────────┐               │
│  │ Provider: DGA   │         │ Provider: SMA   │               │
│  │ Frequency:      │         │ Frequency:      │               │
│  │   hourly        │         │   daily         │               │
│  └────────┬────────┘         └────────┬────────┘               │
│           │                           │                          │
│           ↓                           ↓                          │
│  7️⃣  CHECK FREQUENCY       8️⃣  CHECK FREQUENCY                  │
│  ┌─────────────────┐         ┌─────────────────┐               │
│  │ Hora = :00?     │         │ Hora = 00:00?   │               │
│  │ ✅ SÍ           │         │ ❌ NO           │               │
│  └────────┬────────┘         └─────────────────┘               │
│           │                                                      │
│           ↓                                                      │
│  9️⃣  QUEUE CELERY TASK                                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ send_compliance_data.delay(                               │   │
│  │     record_id=123,                                        │   │
│  │     compliance_config_id=DGA_CONFIG_ID                    │   │
│  │ )                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                               │                                   │
└──────────────────────────────┼───────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│                    CELERY TASK                                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  🔟 BUILD PAYLOAD FROM TEMPLATE                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Template DGA:                                             │   │
│  │ {                                                          │   │
│  │   "codigo_obra": "{config.codigo_obra}",                  │   │
│  │   "caudal": "{record.data.flow}",                         │   │
│  │   "fecha": "{record.timestamp}"                           │   │
│  │ }                                                          │   │
│  │                                                            │   │
│  │ Resultado:                                                │   │
│  │ {                                                          │   │
│  │   "codigo_obra": "ND-0401-1234",                          │   │
│  │   "caudal": 12.5,                                         │   │
│  │   "fecha": "2026-01-20T15:00:00"                          │   │
│  │ }                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                               │                                   │
│                               ↓                                   │
│  1️⃣1️⃣ GET AUTH CREDENTIALS                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ config.get_effective_credentials()                        │   │
│  │ • Si tiene override → usa override                        │   │
│  │ • Si no → usa credentials del provider                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                               │                                   │
│                               ↓                                   │
│  1️⃣2️⃣ AUTHENTICATE                                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Según auth_method del provider:                           │   │
│  │ • Bearer → headers['Authorization'] = f'Bearer {token}'   │   │
│  │ • OAuth2 → POST /auth → get token → Bearer               │   │
│  │ • Basic → base64(user:pass)                               │   │
│  │ • API Key → headers['X-API-Key'] = key                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                               │                                   │
│                               ↓                                   │
│  1️⃣3️⃣ SEND HTTP REQUEST                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ POST https://dga.mop.gob.cl/api/ufs/13/procesos/...      │   │
│  │ Headers: {Authorization: Bearer ...}                      │   │
│  │ Body: {payload generado}                                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                               │                                   │
│                ┌──────────────┴──────────────┐                   │
│                ↓                             ↓                   │
│  1️⃣4️⃣ SUCCESS ✅              1️⃣5️⃣ ERROR ❌                      │
│  ┌───────────────┐           ┌───────────────┐                 │
│  │ Extract       │           │ Record error  │                 │
│  │ voucher from  │           │ in config     │                 │
│  │ response      │           │               │                 │
│  │               │           │ Retry with    │                 │
│  │ config.       │           │ exponential   │                 │
│  │ record_       │           │ backoff       │                 │
│  │ success()     │           │               │                 │
│  └───────────────┘           └───────────────┘                 │
│         │                             │                          │
│         └─────────────┬───────────────┘                          │
│                       ↓                                          │
│  1️⃣6️⃣ UPDATE TELEMETRY RECORD                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ record.compliance_status = {                              │   │
│  │   'dga': {                                                │   │
│  │     'sent': True,                                         │   │
│  │     'voucher': 'ABC123',                                  │   │
│  │     'sent_at': '2026-01-20T15:01:23'                      │   │
│  │   }                                                        │   │
│  │ }                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🎬 Ejemplo Paso a Paso: Configurar Punto para DGA

### Paso 1: Verificar/Crear Proveedor DGA

```
Django Admin
  → Compliance Providers
  → ¿Existe "DGA"?
     ├─ ✅ SÍ → Ir a Paso 2
     └─ ❌ NO → Click "Add Compliance Provider"

═══════════════════════════════════════════════════════════════════

Form: Add Compliance Provider

╔═══════════════════════════════════════════════════════════════╗
║                   INFORMACIÓN BÁSICA                           ║
╠═══════════════════════════════════════════════════════════════╣
║ Name: * dga                                                    ║
║ Display Name: * DGA - Dirección General de Aguas              ║
║ Description: Sistema de reporte automático a la DGA           ║
║ Service Type: [Derechos de Agua ▼]                            ║
╠═══════════════════════════════════════════════════════════════╣
║                        CONEXIÓN                                ║
╠═══════════════════════════════════════════════════════════════╣
║ Base URL: * https://dga.mop.gob.cl/api                        ║
║ Auth Endpoint: /v1/auth                                        ║
║ Data Endpoint Template: * /ufs/{uf_id}/procesos/{process_id}/ ║
║                           registros                            ║
║ Timeout Seconds: 30                                            ║
╠═══════════════════════════════════════════════════════════════╣
║                     AUTENTICACIÓN                              ║
╠═══════════════════════════════════════════════════════════════╣
║ Auth Method: [OAuth2 (user/pass → token) ▼]                   ║
║                                                                ║
║ Auth Config (JSON):                                            ║
║ {                                                              ║
║   "username": "tu_rut",                                        ║
║   "password": "tu_clave",                                      ║
║   "token_field": "token"                                       ║
║ }                                                              ║
╠═══════════════════════════════════════════════════════════════╣
║                  PAYLOAD Y RESPUESTA                           ║
╠═══════════════════════════════════════════════════════════════╣
║ Payload Template (JSON):                                       ║
║ {                                                              ║
║   "codigo_obra": "{config.codigo_obra}",                       ║
║   "caudal": "{record.data.flow}",                              ║
║   "volumen": "{record.data.total}",                            ║
║   "fecha": "{record.timestamp}",                               ║
║   "rut_informante": "{config.rut_informante}",                 ║
║   "dispositivo_id": "{config.dispositivo_id}"                  ║
║ }                                                              ║
║                                                                ║
║ Response Mapping (JSON):                                       ║
║ {                                                              ║
║   "success_field": "status",                                   ║
║   "success_value": "ok",                                       ║
║   "voucher_field": "comprobante",                              ║
║   "message_field": "mensaje"                                   ║
║ }                                                              ║
╠═══════════════════════════════════════════════════════════════╣
║               CONFIGURACIÓN REQUERIDA                          ║
╠═══════════════════════════════════════════════════════════════╣
║ Required Fields (JSON):                                        ║
║ [                                                              ║
║   {                                                            ║
║     "name": "codigo_obra",                                     ║
║     "type": "string",                                          ║
║     "label": "Código de Obra",                                 ║
║     "help": "Código ND asignado por DGA"                       ║
║   },                                                           ║
║   {                                                            ║
║     "name": "rut_informante",                                  ║
║     "type": "string",                                          ║
║     "label": "RUT Informante"                                  ║
║   },                                                           ║
║   {                                                            ║
║     "name": "uf_id",                                           ║
║     "type": "string",                                          ║
║     "label": "ID Unidad Fiscalizable"                          ║
║   },                                                           ║
║   {                                                            ║
║     "name": "process_id",                                      ║
║     "type": "string",                                          ║
║     "label": "ID Proceso DGA"                                  ║
║   },                                                           ║
║   {                                                            ║
║     "name": "dispositivo_id",                                  ║
║     "type": "string",                                          ║
║     "label": "ID Dispositivo Registrado en DGA"                ║
║   }                                                            ║
║ ]                                                              ║
╠═══════════════════════════════════════════════════════════════╣
║            FRECUENCIA Y REINTENTOS                             ║
╠═══════════════════════════════════════════════════════════════╣
║ Submission Frequency: [Cada hora ▼]                            ║
║ Max Retries: 3                                                 ║
║ Retry Delay Seconds: 60                                        ║
╠═══════════════════════════════════════════════════════════════╣
║                        ESTADO                                  ║
╠═══════════════════════════════════════════════════════════════╣
║ ☑️ Is Active                                                   ║
║ Documentation URL: https://dga.mop.gob.cl/docs                 ║
╚═══════════════════════════════════════════════════════════════╝

[Save and continue editing]  [Save and add another]  [Save]
```

### Paso 2: Configurar Punto

```
Django Admin
  → Telemetry
  → Catchment Points
  → [Buscar tu punto: "Pozo ABC"]
  → Click para editar

═══════════════════════════════════════════════════════════════════

Scroll hasta el final del form...

╔═══════════════════════════════════════════════════════════════╗
║          COMPLIANCE CONFIGURATIONS (Inline)                    ║
╠═══════════════════════════════════════════════════════════════╣
║                                                                ║
║ [No hay configuraciones de compliance]                         ║
║                                                                ║
║ [+ Add another Point Compliance Config]  ← Click aquí         ║
╚═══════════════════════════════════════════════════════════════╝

Después de click...

╔═══════════════════════════════════════════════════════════════╗
║          COMPLIANCE CONFIGURATION #1                           ║
╠═══════════════════════════════════════════════════════════════╣
║ Provider: [DGA - Dirección General de Aguas ▼] *               ║
║ Data Source: [Telemetría Automática ▼]                         ║
║                                                                ║
║ Config Data (JSON): *                                          ║
║ {                                                              ║
║   "codigo_obra": "ND-0401-1234",                               ║
║   "rut_informante": "12345678-9",                              ║
║   "nombre_informante": "Juan Pérez",                           ║
║   "uf_id": "13",                                               ║
║   "process_id": "PROC-2024-001",                               ║
║   "dispositivo_id": "12180",                                   ║
║   "caudal_otorgado": 10.5,                                     ║
║   "tipo_derecho": "Consuntivo Permanente"                      ║
║ }                                                              ║
║                                                                ║
║ Credentials Override (JSON): (opcional)                        ║
║ {                                                              ║
║   "username": "otro_rut@dga.cl",                               ║
║   "password": "otra_clave"                                     ║
║ }                                                              ║
║                                                                ║
║ ☑️ Is Active                                                   ║
║ ☑️ Send Compliance  ← ¡IMPORTANTE! Habilita envío automático  ║
║                                                                ║
║ [🗑️ DELETE]                                                    ║
╠═══════════════════════════════════════════════════════════════╣
║ [+ Add another Point Compliance Config]                        ║
╚═══════════════════════════════════════════════════════════════╝

[Save]  ← Click para guardar
```

### Paso 3: (Opcional) Agregar SMA al Mismo Punto

```
Mismo form, scroll abajo...

[+ Add another Point Compliance Config]  ← Click

╔═══════════════════════════════════════════════════════════════╗
║          COMPLIANCE CONFIGURATION #2                           ║
╠═══════════════════════════════════════════════════════════════╣
║ Provider: [SMA - Superintendencia del Medio Ambiente ▼] *      ║
║ Data Source: [Telemetría Automática ▼]                         ║
║                                                                ║
║ Config Data (JSON): *                                          ║
║ {                                                              ║
║   "res_id": "RES-2024-001",                                    ║
║   "empresa_rut": "98765432-1",                                 ║
║   "faena_nombre": "Pozo ABC",                                  ║
║   "coordenadas_utm": {                                         ║
║     "norte": 6300000,                                          ║
║     "este": 350000                                             ║
║   }                                                            ║
║ }                                                              ║
║                                                                ║
║ ☑️ Is Active                                                   ║
║ ☑️ Send Compliance                                             ║
╚═══════════════════════════════════════════════════════════════╝

[Save]
```

**✅ ¡Listo! El punto ahora envía automáticamente a DGA (cada hora) y SMA (según su frecuencia)**

---

## 📊 Vista de Listado

```
Django Admin → Point Compliance Configs → Change List

╔═══════════════════════════════════════════════════════════════════════════════╗
║ Point Compliance Configurations                                               ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║ Filters:                                                                      ║
║ ☐ Provider: All                                                               ║
║   ☑️ DGA                                                                       ║
║   ☐ SMA                                                                       ║
║   ☐ INDH                                                                      ║
║ ☐ Data Source: All                                                            ║
║ ☐ Send Compliance: All                                                        ║
║ ☐ Is Active: All                                                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║ Point          │ Provider │ Source     │ Send │ Active │ Success │ Last Sub   ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║ ✅ Pozo ABC    │ DGA      │ Telemetry  │ ☑️   │ ☑️     │ 98.5%  │ 2h ago     ║
║ ✅ Pozo ABC    │ SMA      │ Telemetry  │ ☑️   │ ☑️     │ 100%   │ 1d ago     ║
║ ❌ Pozo XYZ    │ DGA      │ Manual     │ ☐    │ ☑️     │ N/A    │ Never      ║
║ ✅ Sensor 01   │ DGA      │ Telemetry  │ ☑️   │ ☑️     │ 75.2%  │ Error: ... ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

## 🎯 Ventajas del Flujo

| Tarea | Tiempo Antes | Tiempo Ahora |
|-------|--------------|--------------|
| Agregar DGA a nuevo punto | 1 hora (código + deploy) | 2 minutos (admin) |
| Cambiar credenciales DGA | 30 min (código + deploy) | 1 minuto (admin) |
| Agregar nuevo compliance (SMA) | 2 días (desarrollo) | 5 minutos (admin) |
| Ver estadísticas envíos | Queries SQL manuales | Click en list view |
| Debugging errores | Logs dispersos | `last_error` field |

---

## 💡 Tips y Trucos

### Ver Estadísticas de un Punto

```
Admin → Catchment Points → [Tu Punto] → Edit
Scroll abajo a "Compliance Configurations"
```

Verás inline con:
- ✅/❌ Estado de cada provider
- Última vez enviado
- Count de errores
- Tasa de éxito

### Debugging Errores

```
Admin → Point Compliance Configs → [Config con error]
```

Campo `Last Error` muestra último mensaje de error completo.

### Deshabilitar Envíos Temporalmente

```
Admin → Point Compliance Config → [Tu config]
☐ Send Compliance  ← Desmarcar
[Save]
```

Los datos se siguen recolectando, pero no se envían.

### Cambiar Frecuencia Global

```
Admin → Compliance Providers → DGA → Edit
Submission Frequency: [Diario ▼]  ← Cambiar de "Cada hora" a "Diario"
[Save]
```

Afecta a TODOS los puntos usando DGA.

### Override de Frecuencia por Punto

(Future feature - agregar `frequency_override` a PointComplianceConfig)

---

¿Quieres que genere el código completo de migración ahora? 😊
