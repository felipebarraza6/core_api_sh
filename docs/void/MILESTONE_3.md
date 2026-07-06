# Milestone 3 — Cumplimiento Multi-Frecuencia y Puntos Superficiales

> Estado: **cerrado** — modelos y servicios listos, tests OK, envío real deshabilitado.  
> Fecha cierre: 2026-07-06  
> Objetivo: dotar a `void` de un motor de cumplimiento regulatorio configurable que soporte frecuencias dinámicas, puntos superficiales y captura de voucher, sin activar envíos en producción.

---

## 1. Contexto

El **Milestone 2** cerró con paridad de procesamiento en shadow mode.  
El **Milestone 3** avanza hacia la replicación completa del comportamiento de cumplimiento legacy (DGA/SMA) con un diseño declarativo:

- Estándares de envío configurables (MAYOR, MEDIO, MENOR, SMA cada 5 min, etc.).
- Soporte nativo para puntos **superficiales** (`medicionSuperficialFlujometro`) además de **subterráneos**.
- Cola de envíos, reintentos y voucher/tracking de respuesta.
- Integración con el pipeline de `ProcessedReading`.

Todo sigue bajo `VOID_AUTOMATION_ENABLED=False`; legacy continúa siendo el único que envía a DGA en producción.

---

## 2. Entregables

| Entregable | Estado |
|---|---|
| Modelo `ComplianceAuthority` (entidad configurable: DGA, SMA, etc.) | ✅ |
| Modelo `ComplianceStandard` (frecuencia dinámica por minuto/hora/día/mes/intervalo) | ✅ |
| Modelo `PointComplianceProfile` (config por punto + entidad + estándar) | ✅ |
| Modelo `ComplianceSubmission` (cola, voucher, retry, respuesta) | ✅ |
| `ComplianceScheduleService` | ✅ |
| `ComplianceService.submit_reading` con validación de estándar | ✅ |
| `DGAComplianceAdapter` con payload subterráneo y superficial | ✅ |
| `SMAComplianceAdapter` con auth por token | ✅ |
| Sync legacy actualizado para poblar estándares y `type_key` | ✅ |
| Tests `void.tests` | ✅ 100/100 OK |
| Envío real a DGA/SMA | ⛔ Deshabilitado por flag |
| Reemplazo de cronjobs legacy | ⛔ Fuera de scope |

---

## 3. Diseño

### 3.1 Modelo de datos

```
ComplianceAuthority
├── code (dga, sma, ...)
├── protocol / auth_type / base_url / auth_url
├── auth_username / auth_password / auth_token
├── protocol_config (endpoints específicos, RUT empresa por defecto)
└── retry_attempts / timeout_seconds

ComplianceStandard
├── code (MAYOR, MEDIO, MENOR, SMA_5, ...)
├── frequency_minutes (referencia SLA)
├── send_minute / send_hour / send_day / send_month
└── minute_interval (ej: 5 → minuto % 5 == 0)

PointComplianceProfile
├── point → ComplianceAuthority (unique_together)
├── standard → ComplianceStandard
├── type_key (SUBTERRANEO / SUPERFICIAL)
├── external_code (código de obra / device id)
├── variable_mapping (mapeo ProcessedReading → payload)
└── aggregate_points, flow_granted, total_granted, region, shac, ...

ComplianceSubmission
├── profile / processed_reading
├── status (pending, sent, confirmed, failed, duplicate, unrecoverable, retrying)
├── payload / response_status / response_body
├── voucher / tracking_id / attempt_number
└── sent_at / confirmed_at / last_retry_at
```

### 3.2 Reglas de schedule

`ComplianceStandard.matches_timestamp(dt)` retorna `True` si todas las reglas configuradas coinciden:

| Campo | Significado |
|---|---|
| `send_minute` | Minuto exacto (0-59) |
| `send_hour` | Hora exacta (0-23) |
| `send_day` | Día exacto del mes (1-31) |
| `send_month` | Mes exacto (1-12) |
| `minute_interval` | Intervalo: `dt.minute % interval == 0` |

Ejemplos:

- **MAYOR**: `send_minute=0` → cada hora en punto.
- **MEDIO**: `send_minute=0, send_hour=0` → todos los días a medianoche.
- **MENOR**: `send_minute=0, send_hour=0, send_day=1` → primero de cada mes.
- **SMA**: `minute_interval=5` → minutos múltiplos de 5.

Si el perfil no tiene estándar asignado, se acepta cualquier timestamp (comportamiento `SIN_ESTANDAR`).

### 3.3 Payload DGA

El adapter decide el endpoint y la estructura según `profile.type_key`:

- `SUBTERRANEO` → `medicionSubterranea` con `nivelFreaticoDelPozo`.
- `SUPERFICIAL` → `medicionSuperficialFlujometro` sin nivel freático.

Incluye metadatos de trazabilidad:

- `_type_dga`
- `_codigo_obra`
- `_timestamp_origen`

### 3.4 Voucher y retry

Cada envío crea una `ComplianceSubmission` en estado `pending`. Si `auto_send=True`, se ejecuta inmediatamente:

- Respuesta 200/201 con comprobante → `confirmed` + `voucher`.
- Respuesta 400 con mensaje de duplicado → `duplicate` + voucher extraído.
- Error de conexión → `failed` / `retrying` según reintentos configurados.

`ComplianceService.process_queue()` recorre submissions pendientes/retrying respetando backoff de 15 minutos.

---

## 4. Tests cubiertos

- `ComplianceStandardTests`: MAYOR, MEDIO, MENOR, intervalo de minutos.
- `DGAAdapterTests`: payload subterráneo y superficial, respuestas 200/duplicado/unrecoverable.
- `SMAAdapterTests`: build payload y envío mock.
- `ComplianceServiceTests`: envío DGA, duplicado, rechazo por estándar, filtro SMA por minuto, procesamiento de cola.

---

## 5. Comandos útiles

```bash
# Tests de void
python manage.py test void.tests --noinput --keepdb

# Sincronizar puntos legacy con perfiles de cumplimiento
python manage.py void_sync_legacy --project-legacy-id <id>

# Procesar cola de cumplimiento (manual, no auto)
python manage.py shell -c "
from void.services import ComplianceService
print(ComplianceService().process_queue())
"
```

---

## 6. Qué NO incluye este milestone

- **Envío real a DGA/SMA:** requiere `VOID_AUTOMATION_ENABLED=True` y autorización explícita.
- **Configuración de proveedores dinámicos para compliance:** el payload y auth se configuran por entidad, pero aún no hay UI/API REST.
- **Migración de clientes/usuarios a `void`:** sigue en roadmap posterior.
- **Reemplazo de cronjobs legacy:** continúan corriendo.

---

## 7. Próximos pasos recomendados (Milestone 4)

1. Implementar API REST de void para `ComplianceAuthority`, `ComplianceStandard`, `PointComplianceProfile`.
2. Validar envío sandbox a DGA con un punto real y `auto_send=True`.
3. Conectar `ComplianceService.submit_reading` al pipeline de `ProcessedReading`.
4. Agregar alertas por fallos recurrentes de compliance.
5. Replicar lógica crítica de `controllers/total.py` en `PipelineService` (resets, monotonicidad, compensación offline).
