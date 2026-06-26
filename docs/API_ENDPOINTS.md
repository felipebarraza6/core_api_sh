# SmartHydro — Catálogo Completo de Endpoints API

> **Generado:** 2026-06-03
> **Base URL:** `https://api.smarthydro.app`
> **Auth:** Bearer Token (`Authorization: Bearer <token>`) excepto donde se indique `AllowAny`.
> **Estado:** Producción activa — 120 tests pasando

---

## 📑 Índice

1. [Auth & Usuarios](#1-auth--usuarios)
2. [Ikolu App (`/api/ik/`)](#2-ikolu-app-apiik)
3. [Legacy Core (`/api/`)](#3-legacy-core-api)
4. [Alertas (`/api/alert_*/`)](#4-alertas)
5. [Tickets de Soporte](#5-tickets-de-soporte)
6. [Reportes (`/api/reports/` & `/reports/`)](#6-reportes)
7. [Management (`/api/management/`)](#7-management)
8. [Compliance & DGA](#8-compliance--dga)
9. [Chatbot](#9-chatbot)
10. [Sistema (health, status, admin, schema)](#10-sistema)
11. [Notas Generales para Frontend](#11-notas-generales-para-frontend)

---

## 1. Auth & Usuarios

### `POST /api/users/login/`
Login legacy. Devuelve token + perfil completo del usuario con puntos anidados.

| Campo | Tipo | Requerido |
|-------|------|-----------|
| `email` | string | ✅ |
| `password` | string | ✅ |

**Response:**
```json
{
  "success": true,
  "message": "Login exitoso",
  "user": { /* perfil completo con CatchmentPoint anidados */ },
  "access_token": "eyJ..."
}
```

---

### `POST /api/users/signup/`
Registro de usuario.

**Auth:** `AllowAny`

---

### `GET /api/users/me/`
Perfil del usuario autenticado (versión ligera).

**Response:**
```json
{
  "user": { /* perfil */ }
}
```

---

### `POST /api/users/change-password/`
Cambio de contraseña.

| Campo | Tipo | Requerido |
|-------|------|-----------|
| `current_password` | string | ✅ |
| `new_password` | string | ✅ |

---

### `GET /api/users/<username>/`
Detalle de usuario (solo dueño de la cuenta o staff).

**Auth:** `IsAuthenticated + IsAccountOwner`

---

### `POST /api/ik/login/` — Login Optimizado (Ikolu)
Versión reducida del login. Devuelve token + resumen liviano de puntos (total, owned_ids, viewed_ids).

| Campo | Tipo | Requerido |
|-------|------|-----------|
| `email` | string | ✅ |
| `password` | string | ✅ |

**Auth:** `AllowAny`
**Throttle:** `LoginRateThrottle`

---

### Password Reset (`django_rest_passwordreset`)

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `POST /api/password_reset/` | POST | Solicitar token de reset |
| `POST /api/password_reset/confirm/` | POST | Confirmar nuevo password |
| `POST /api/password_reset/validate_token/` | POST | Validar token |
| `POST /api/ik/auth/password-reset/` | POST | Idem, vía Ikolu |
| `POST /api/ik/auth/password-reset/confirm/` | POST | Idem |
| `POST /api/ik/auth/password-reset/validate/` | POST | Idem |

---

## 2. Ikolu App (`/api/ik/`)

API optimizada para el Centro de Control (app móvil/web moderna). Todos los endpoints requieren `IsAuthenticated` salvo donde se indique.

### Batch

#### `POST /api/ik/batch/telemetry/`
Telemetría multi-punto en una sola llamada.

| Campo | Tipo | Requerido | Límite |
|-------|------|-----------|--------|
| `point_ids` | int[] | ✅ | Puntos del usuario |
| `hours` | int | ❌ | default 1, max 168 |

**Throttle:** `BatchRateThrottle` (10/min)

---

#### `POST /api/ik/batch/stats/`
Stats agregados multi-punto.

| Campo | Tipo | Requerido | Límite |
|-------|------|-----------|--------|
| `point_ids` | int[] | ✅ | Puntos del usuario |
| `days` | int | ❌ | default 30, max 365 |

**Throttle:** `BatchRateThrottle` (10/min)

---

### Points & Dashboard

#### `GET /api/ik/points_summary/`
Resumen de **todos** los puntos del usuario + última telemetría + alertas + config DGA + provider.

| Query Param | Tipo | Default | Descripción |
|-------------|------|---------|-------------|
| `limit` | int | — | Paginación opcional (max 200) |
| `offset` | int | 0 | Paginación opcional |

**Throttle:** `SummaryRateThrottle`

---

#### `GET /api/ik/point/<id>/summary/`
Resumen de un punto específico (estado, últimos valores, config, esquemas, variables).

**Throttle:** `SummaryRateThrottle`

---

#### `GET /api/ik/my_points/`
Lista ultra-liviana de puntos (id, título, proyecto, cliente, frecuencia, telemetry flag, DGA compliance, owner/viewer) para dropdowns/selects.

| Query Param | Tipo | Default | Descripción |
|-------------|------|---------|-------------|
| `limit` | int | — | Máximo 500 |

---

#### `GET /api/ik/dashboard_stats/`
KPIs del Centro de Control: totales, activos, desconectados, compliance, últimos 7 días por punto (consumo, caudal, nivel), warnings (resets/system events), chat quota.

**Throttle:** `DashboardRateThrottle`

---

#### `GET /api/ik/point/<id>/calendar/`
Datos de los últimos N días para calendario/visualización de consumo.

| Query Param | Tipo | Default | Descripción |
|-------------|------|---------|-------------|
| `days` | int | 7 | Max 30 |

---

#### `GET /api/ik/point/<id>/variables/`
Mapeo de variables del punto: `id`, `str_variable`, `label`, `type_variable`, `display_key`, `min_value`, `max_value`. Usado para interpretar `variable_values` en telemetría.

**Throttle:** `SummaryRateThrottle`

---

#### `GET /api/ik/point/<id>/records/`
Registros de telemetría por rango de fechas. Devuelve campos esenciales + `total_raw` (sin addition).

| Query Param | Tipo | Default | Descripción |
|-------------|------|---------|-------------|
| `start` | ISO datetime | — | Inicio del rango |
| `end` | ISO datetime | — | Fin del rango |

**Límites:** máx 31 días, máx 500 registros.

---

#### `GET /api/ik/point/<id>/config/`
Config liviana del punto: d1-d6, addition, is_telemetry, offsets, límites de procesamiento.

---

#### `GET /api/ik/point/<id>/gaps/`
Gap detection — detecta huecos de telemetría **sin modificar BD**.

| Query Param | Tipo | Default | Descripción |
|-------------|------|---------|-------------|
| `start` | ISO datetime | primer registro | Inicio del análisis |
| `end` | ISO datetime | último registro | Fin del análisis |

---

### Compliance

#### `GET /api/ik/compliance/`
Compliance DGA/SMA detallado: código, estándar, tipo de captación, caudal/total autorizados, consumo anual, % consumido, historial de excedencias, warnings preventivos (`safe`/`warning`/`critical`/`unknown`), último envío exitoso (voucher, fecha). Stats globales incluyen `with_warnings` y `with_critical`.

**Throttle:** `DashboardRateThrottle`

---

### Backfill Telemetría

#### `POST /api/ik/telemetry/backfill/`
Re-sync histórico completo (TWIN/NOVUS). Ingesta datos del provider para un rango y aplica procesamiento unificado: caudal L/s, nivel+offset, totales en cascada, diffs. Rango máximo 30 días.

| Campo | Tipo | Requerido |
|-------|------|-----------|
| `point_id` | int | ✅ |
| `start` | ISO datetime | ✅ |
| `end` | ISO datetime | ✅ |

**Auth:** `IsStaffOrSuperUser`
**Throttle:** `BackfillRateThrottle`

---

### Anuncios Públicos

#### `GET /api/ik/announcements/public/`
Anuncios globales activos (mantenimientos, novedades). Sin autenticación.

**Auth:** `AllowAny`
**Throttle:** `PublicReadRateThrottle` (100/h)

---

### Chat Interpretativo

#### `POST /api/ik/chat/client/general_stats/`
Chat con Gemini interpretando stats del cliente. El backend inyecta automáticamente el dashboard del usuario como contexto.

| Campo | Tipo | Requerido |
|-------|------|-----------|
| `message` | string | ✅ |

**Límite:** 12 preguntas diarias por usuario (quota en Redis).
**Throttle:** `DashboardRateThrottle`

---

### Eventos del Sistema

#### `GET /api/ik/system-events/summary/`
Resumen de eventos del sistema (`SystemEvent`): conteos por severidad, tipo, punto, timeline y eventos recientes.

| Query Param | Tipo | Default | Descripción |
|-------------|------|---------|-------------|
| `days` | int | 7 | Rango de días |
| `point_id` | int | — | Filtrar por punto |

**Throttle:** `DashboardRateThrottle`

---

## 3. Legacy Core (`/api/`)

DefaultRouter de DRF. CRUDs completos sobre todos los modelos del dominio. Todos requieren `IsAuthenticated`.

### Clientes

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/api/client/` | GET, POST | Listar/crear clientes |
| `/api/client/<id>/` | GET, PUT, PATCH, DELETE | Detalle cliente |
| `/api/client/all/` | GET | Todos sin paginación (limit 500 default, max 1000, cache 5 min) |
| `/api/client/with-projects/` | GET | Clientes con proyectos anidados |

**Filtros:** `?search=`, `?ordering=`

---

### Proyectos

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/api/project_catchments/` | GET, POST | Listar/crear proyectos |
| `/api/project_catchments/<id>/` | GET, PUT, PATCH, DELETE | Detalle |
| `/api/project_catchments/all/` | GET | Todos sin paginación (limit 500 default, max 1000, cache 5 min) |

**Filtros:** `?client=`

---

### Puntos de Captación

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/api/catchment_point/` | GET, POST | Listar/crear puntos |
| `/api/catchment_point/<id>/` | GET, PUT, PATCH, DELETE | Detalle (usa `CatchmentPointIkoluSerializer`: módulos m1-m4, DGA, config, archivos, alertas) |
| `/api/catchment_point/all/` | GET | Todos sin paginación (limit 500 default, max 1000) |

**Filtros:** `?project=`, `?search=` (título/proyecto/cliente/owner), `?ordering=`

---

### Esquemas & Variables

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/api/schemes_catchment/` | GET, POST | Esquemas de punto |
| `/api/schemes_catchment/<id>/` | GET, PUT, PATCH, DELETE | Detalle |
| `/api/variable/` | GET, POST | Variables |
| `/api/variable/<id>/` | GET, PUT, PATCH, DELETE | Detalle |

**Filtros (variables):** `?scheme_catchment=`, `?provider=`, `?search=` (nombre/label/token)

---

### Configuración de Puntos

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/api/profile_data_config_catchment/` | GET, POST | Config de datos (d1-d6, token, is_telemetry, addition/offset, replicate_on_missing, límites: max_diff, max_flow, max_gap, reconnection_threshold) |
| `/api/dga_data_config_catchment/` | GET, POST | Config DGA/SMA (send_dga, estándar, tipo, código, caudal/total otorgado, SHAC, región, credenciales, send_sma, sma_device_id, puntos agregados) |
| `/api/profile_ikolu_catchment/` | GET, POST | Perfiles Ikolu (módulos m1-m7, suscripciones, fechas) |
| `/api/register_persons/` | GET, POST | Personas registradas |
| `/api/type_file_catchment/` | GET, POST | Tipos de archivo |
| `/api/file_catchment/` | GET, POST | Archivos adjuntos al punto |

**Filtros comunes:** `?point_catchment=`, `?internal=` (type_file)

---

### Notificaciones (Legacy)

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/api/notifications_catchment/` | GET, POST | Alertas umbral + tickets legacy |
| `/api/notifications_catchment/<id>/` | GET, PUT, PATCH, DELETE | Detalle (incluye `stats`: disparos, histórico de mediciones) |
| `/api/response_notifications_catchment/` | GET, POST | Disparos/respuestas legacy |
| `/api/response_notifications_catchment/<id>/` | GET, PUT, PATCH, DELETE | Detalle (si la notificación es alerta umbral sincronizada con `AlertRule`, devuelve `AlertTrigger` mapeados a formato legacy) |

**Nota:** Las alertas umbral (`type_notification=ALERT`) se sincronizan bidireccionalmente con `AlertRule` vía signals. El frontend legacy puede seguir usando estos endpoints.

---

### InteractionDetail (Telemetría)

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/api/interaction_detail_json/` | GET, POST, PUT, PATCH, DELETE | CRUD telemetría (JSON) |
| `/api/interaction_detail/` | GET | Descarga **XLSX** telemetría (columnas dinámicas según variables del punto) |
| `/api/interaction_detail_dga/` | GET | Descarga **XLSX DGA** (formato comprobante DGA, sin procesamiento) |
| `/api/interaction_detail_override/` | GET, POST, PUT, PATCH, DELETE | Override telemetría (sin paginación) |
| `/api/interaction_detail_override_month/` | GET, POST, PUT, PATCH, DELETE | Override mensual (sin paginación, subquery último registro por día) |
| `/api/interaction_detail_override_month_xlsx/` | GET | Override mensual XLSX (único registro por día) |

**Filtros:** `?catchment_point=`, `?date_time_medication=`, `?date_time_medication__gte=`, `?date_time_medication__lte=`, `?hour=`, `?year=`, `?month=`, `?day=`, `?daily=`, `?is_error=`, `?send_dga=`, `?limit=`, `?offset=`

**Nota de seguridad:** Si NO se especifica filtro de fecha, el listado se corta a:
- `interaction_detail_json`: últimas 24h (limit 1000, max 5000)
- `interaction_detail_override`: últimos 7 días (limit 1000, max 5000)
- `interaction_detail_override_month`: últimos 90 días (limit 1000, max 5000)

---

### Proveedores

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/api/telemetry_providers/` | GET | Proveedores de telemetría (TDATA, TheThings, Tago, Generic JSON). Solo lectura. |
| `/api/compliance_providers/` | GET | Proveedores de compliance (DGA, SMA). Solo lectura. |
| `/api/counter_reset_logs/` | GET | Logs de reset de contadores (auditoría). Solo lectura. |

**Filtros:** `?handler=`, `?protocol=`, `?auth_type=`, `?is_active=` (providers); `?catchment_point=`, `?reset_type=`, `?detected_by=` (reset logs)

---

## 4. Alertas

Subsistema de alertas nuevo (`AlertRule` + `AlertChannel` + `AlertTrigger` + `SystemEvent`). Corre en paralelo al sistema legacy.

### AlertRule (`/api/alert_rules/`)
CRUD completo de reglas de alerta configurables.

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `GET /api/alert_rules/` | GET, POST | Listar/crear reglas |
| `GET /api/alert_rules/<id>/` | GET, PUT, PATCH, DELETE | Detalle (incluye canales anidados en retrieve) |

**Filtros:** `?point_catchment=`, `?target_type=`, `?variable_type=`, `?is_active=`, `?check_frequency_minutes=`, `?check_frequency_minutes__lte=`, `?check_frequency_minutes__gte=`, `?search=`, `?ordering=`

**Target types:** `THRESHOLD_MAX`, `THRESHOLD_MIN`, `NO_DATA`, `DISCONNECTION`, `RECONNECTION`, `PROCESSING_ERROR`, `RATE_OF_CHANGE`, `DEVIATION`, `SCHEDULED_REPORT`

**Campos principales (POST/PUT):**
```json
{
  "name": "Caudal alto",
  "point_catchment": 1,
  "target_type": "THRESHOLD_MAX",
  "variable_type": "CAUDAL",
  "threshold_value": "100.00",
  "check_frequency_minutes": 5,
  "cooldown_minutes": 60,
  "severity": "WARNING",
  "is_active": true,
  "no_data_minutes": 60,
  "max_disconnection_days": 3
}
```

---

### AlertChannel (`/api/alert_channels/`)
Canales de notificación por regla.

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `GET /api/alert_channels/` | GET, POST | Listar/crear canales |
| `GET /api/alert_channels/<id>/` | GET, PUT, PATCH, DELETE | Detalle |

**Filtros:** `?alert_rule=`, `?channel_type=`, `?is_active=`, `?search=`, `?ordering=`

**Channel types:** `EMAIL`, `GOOGLE_CHAT`, `WEBHOOK`, `SMS`

---

### AlertTrigger (`/api/alert_triggers/`)
Historial de disparos. Solo lectura y update parcial (acknowledge).

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `GET /api/alert_triggers/` | GET | Listar triggers |
| `GET /api/alert_triggers/<id>/` | GET, PATCH | Detalle + ack |

**Filtros:** `?alert_rule=`, `?notification_sent=`, `?is_acknowledged=`, `?triggered_at=`, `?triggered_at__date__gte=`, `?triggered_at__date__lte=`

---

### SystemEvent (`/api/system_events/`)
Eventos del sistema generados automáticamente.

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `GET /api/system_events/` | GET | Listar eventos |
| `GET /api/system_events/<id>/` | GET | Detalle |

**Filtros:** `?event_type=`, `?severity=`, `?catchment_point=`, `?created_at__date__gte=`, `?created_at__date__lte=`

**Event types:** `COUNTER_RESET`, `DISCONNECTION`, `RECONNECTION`, `MEASUREMENT_ERROR`, `MASSIVE_JUMP_BLOCKED`, `TOKEN_REFRESH`, `API_ERROR`

---

## 5. Tickets de Soporte

### Legacy (`/api/`)

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/api/notifications_catchment/` | GET, POST | Crear ticket vía sistema legacy |
| `/api/response_notifications_catchment/` | GET, POST | Respuestas a tickets legacy |

### Ikolu (`/api/ik/tickets/`)

| Endpoint | Métodos | Auth | Descripción |
|----------|---------|------|-------------|
| `GET /api/ik/tickets/` | GET, POST | Token | Listar/crear tickets. Filtros: `status`, `origin`, `category`, `priority`, `assigned_to`, `point`, `search` |
| `GET /api/ik/tickets/<id>/` | GET, PATCH | Token | Detalle/actualización parcial. Clientes solo editan título/descripción/prioridad/categoría. Staff puede todo. |
| `POST /api/ik/tickets/<id>/assign/` | POST | Staff only | Asignar ticket a usuario |
| `POST /api/ik/tickets/<id>/status/` | POST | Staff only | Cambiar estado (maneja `RESUELTO`/`CERRADO` con fechas) |
| `GET /api/ik/tickets/<id>/comments/` | GET, POST | Token | Comentarios. Staff puede notas internas; clientes no. Marca SLA responded al primer comentario de staff. |
| `GET /api/ik/tickets/<id>/attachments/` | GET, POST | Token | Adjuntos. Validación tipo/tamaño (max 10 MB) |
| `GET /api/ik/tickets/stats/` | GET | Token | Dashboard de soporte: conteos por estado, categoría, prioridad, origen, SLA vencidos |

**Estados:** `ABIERTO`, `EN_ANALISIS`, `ESPERA_CLIENTE`, `ESPERA_PROVEEDOR`, `RESUELTO`, `CERRADO`, `CANCELADO`
**Categorías:** `SOFTWARE`, `HARDWARE`, `CONECTIVIDAD`, `DGA`, `TELEMETRIA`, `OTRO`
**Prioridades:** `BAJA`, `MEDIA`, `ALTA`, `CRITICA`
**Orígenes:** `APP`, `WEB`, `CHAT`, `ALERTA`, `STAFF`

**Throttle:** `TicketRateThrottle`

---

## 6. Reportes

### Excel (`/api/reports/`)

| Endpoint | Método | Query Params | Descripción |
|----------|--------|--------------|-------------|
| `GET /api/reports/by-project/` | GET | `?project_id=` | Excel análisis por proyecto |
| `GET /api/reports/by-point/` | GET | `?point_id=&year=&month=` | Excel análisis por punto |
| `GET /api/reports/last-month/` | GET | `?project_id=&point_ids=` | Excel último mes |
| `GET /api/reports/last-year/` | GET | `?project_id=&point_ids=` | Excel último año |
| `GET /api/reports/annual-compressed/` | GET | `?project_id=&point_ids=` | Excel anual comprimido |

**Response:** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

---

### JSON (`/api/reports/json/*`)

| Endpoint | Método | Query Params | Descripción |
|----------|--------|--------------|-------------|
| `GET /api/reports/json/by-project/` | GET | `?project_id=&point_ids=` | Resumen puntos últimos 30 días |
| `GET /api/reports/json/by-point/` | GET | `?point_id=&year=&month=` | Datos diarios agregados |
| `GET /api/reports/json/last-month/` | GET | `?project_id=&point_ids=` | Datos último mes |
| `GET /api/reports/json/last-year/` | GET | `?project_id=&point_ids=` | Datos último año (mensual) |
| `GET /api/reports/json/annual-compressed/` | GET | `?project_id=&point_ids=` | Resumen anual comprimido |

---

### Reporte Puntos Activos (`/reports/active-points/`)

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `GET /reports/active-points/` | GET | Excel con todos los puntos activos y última telemetría |

**Auth:** `IsAuthenticated` (Session + Basic)

---

## 7. Management

| Endpoint | Método | Descripción | Auth |
|----------|--------|-------------|------|
| `GET /api/management/system_status/` | GET | Stats globales: puntos totales, telemetría activa, desconectados, registros 24h, notificaciones activas, cola DGA, errores | `IsAuthenticated` |
| `GET /api/management/points_status/` | GET | Estado detallado de puntos. Query: `project`, `client`, `disconnected`, `active_telemetry`. Incluye última interacción y provider | `IsAuthenticated` |
| `GET /api/management/telemetry_metrics/` | GET | Métricas agregadas de telemetría. Query: `point`, `days` (default 7). Incluye avg/max/min flow, consumo total, registros por día/hora | `IsAuthenticated` |
| `POST /api/management/toggle_telemetry/` | POST | Activa/desactiva telemetría de un punto (`point_id`, `enabled`) | `IsAuthenticated` |
| `GET /api/management/dga_queue_status/` | GET | Estado cola DGA: total, por punto, errores, registros antiguos | `IsStaffOrSuperUser` |
| `POST /api/management/clear_dga_queue/` | POST | Limpia cola DGA. Body opcional: `point_id`, `only_errors` | `IsStaffOrSuperUser` |
| `POST /api/management/requeue_dga/` | POST | Reagrega registros a cola DGA. Body: `point_id`, `start_date`, `end_date`, `only_errors` | `IsStaffOrSuperUser` |
| `POST /api/management/update_point_frequency/` | POST | Cambia frecuencia de punto (`1`, `5`, `10`, `60` minutos) | `IsAuthenticated` |
| `GET /api/management/notifications_summary/` | GET | Resumen de notificaciones. Query: `days` (default 7) | `IsAuthenticated` |
| `GET /api/management/system_map/` | GET | **Staff only**. Mapa completo del sistema: modelos, endpoints, cronjobs, estado Django/DB/Redis | `IsStaffOrSuperUser` |
| `GET /api/management/resources_status/` | GET | **Staff only**. Estado del servidor: CPU, memoria, disco, uptime, Docker, health checks de servicios externos (Twin, Nettra, Tago, DGA, SMA), estado de cronjobs basado en logs | `IsStaffOrSuperUser` |

---

## 8. Compliance & DGA

### `GET /compliance/dga/verify/`
Verifica un comprobante DGA interno por número.

| Query Param | Tipo | Requerido |
|-------------|------|-----------|
| `numero_comprobante` | string | ✅ |
| `codigo_obra` | string | ❌ |
| `tipo_dga` | string | ❌ |

**Auth:** `IsAuthenticated`

---

## 9. Chatbot

### App Chat (`/api/chat/`)

#### `POST /api/chat/`
Chatbot inteligente para la app web/móvil.

| Campo | Tipo | Requerido |
|-------|------|-----------|
| `message` | string | ✅ |
| `conversation_id` | string | ❌ (UUID generado automáticamente si no se envía) |

**Motor:** Google Gemini (gemini-2.0-flash) + Intent Router determinista.
**Contexto:** Redis (TTL 15 min).
**Tools:** Búsqueda de puntos, mediciones, historial, compliance DGA, alertas, rankings, anomalías, comparaciones, tendencias.
**Scoped:** Usuarios normales solo ven sus puntos (owner/viewer); staff ve todo.
**Caché:** Respuestas cacheadas para queries repetidas.

---

### Google Chat Webhook (`/api/chat-bot/`)

#### `POST /api/chat-bot/`
Webhook para integración con Google Chat. Soporta cards interactivas y slash commands.

**Auth:** Token de verificación de Google Chat (configurado en el bot).

---

## 10. Sistema

### Health & Status

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `GET /` | GET | `AllowAny` | Info básica del servicio y endpoints disponibles |
| `GET /health/` | GET | `AllowAny` | Health check: `{"status":"ok","service":"SmartHydro API"}` |
| `GET /status/` | GET | `login_required` | Status JSON (API, DB, Redis, cronjobs) |
| `GET /status/dashboard/` | GET | `login_required` | HTML dashboard de status |

---

### Documentación Técnica

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `GET /docs/` | GET | — | Portal de documentación técnica (HTML estático) |
| `GET /docs/sales/` | GET | — | Portal de ventas/casos de uso |
| `GET /docs/math/` | GET | — | Portal de contexto matemático |

---

### OpenAPI Schema

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `GET /api/schema/` | GET | — | OpenAPI Schema (Spectacular) |
| `GET /api/schema/swagger-ui/` | GET | — | Swagger UI |
| `GET /api/schema/redoc/` | GET | — | Redoc |

---

### Admin Dashboards

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `GET /admin/dashboard/` | GET | Staff | Dashboard personalizado del admin (métricas de obras DGA, % conectados/desconectados, desglose por proveedor y estándar, veracidad de caudal, errores imposibles, cola DGA, notificaciones pendientes, registros recientes con filtros) |
| `GET /admin/telemetry-monitoring/` | GET | Staff | Vista HTML de monitoreo de telemetría en tiempo real |
| `GET /admin/telemetry-monitoring/api/` | GET | Staff | API JSON para el monitoring grid |
| `GET /admin/telemetry-monitoring/api/point/<id>/records/` | GET | Staff | Registros de un punto para el monitoring |
| `GET /admin/dga-compliance-report/` | GET | Staff | Reporte de compliance DGA (vista admin) |
| `GET /admin/` | GET | Staff | Django Admin estándar |

---

### Herramientas Técnicas (Telemetry Reprocessor)

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `POST /api/telemetry-reprocessor/` | POST | Staff | Auditoría y corrección de telemetría. Dry-run por defecto. Requiere `apply=true` para modificar DB. Ver `docs/API_TELEMETRY_REPROCESSOR.md` |

---

## 11. Notas Generales para Frontend

### Paginación
- Default: `PageNumberPagination`, `PAGE_SIZE=10`
- Endpoints `all/` no usan paginación pero tienen límite de seguridad (500 default, max 1000)
- Se puede forzar límite con `?limit=` (validado en backend)

### Filtros
- Todos los listados soportan `?search=` y `?ordering=` donde se indique.
- Los filtros de fecha usan el formato ISO: `?date_time_medication__gte=2026-05-01T00:00:00`
- Los filtros de fecha corta usan: `?year=2026&month=5&day=15`

### Throttling
| Clase | Rate | Endpoints |
|-------|------|-----------|
| `AnonRateThrottle` | 100/h | Login legacy |
| `LoginRateThrottle` | 100/h | `/api/ik/login/` |
| `BatchRateThrottle` | 10/min | Batch telemetry, Batch stats |
| `SummaryRateThrottle` | 60/min | Points summary, Point summary, Variables, My points |
| `DashboardRateThrottle` | 30/min | Dashboard stats, Compliance, Chat client, System events |
| `PublicReadRateThrottle` | 100/h | Anuncios públicos |
| `TicketRateThrottle` | 60/min | Tickets (todos) |
| `BackfillRateThrottle` | 5/min | Backfill telemetry |

### Formatos
- Todos los endpoints DRF aceptan `?format=json` o header `Accept: application/json`
- Algunos endpoints soportan `.json` en la URL (ej: `/api/users/me.json`)
- Exportaciones Excel usan `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

### Permisos
- **Base:** `IsAuthenticated` en casi toda la API.
- **Staff-only:** `system_map`, `resources_status`, `dga_queue_status`, `clear_dga_queue`, `requeue_dga`, asignación de tickets, cambio de estado de tickets, backfill, admin dashboards.
- **Propiedad:** Usuarios normales solo ven puntos donde son `owner_user` o `users_viewers`. Staff/superuser ven todo.

### Variables de Negocio
- `CAUDAL` — Caudal instantáneo en L/s
- `NIVEL` — Nivel freático en metros
- `TOTALIZADO` — Total acumulado de pulsos (con addition/compensación)
- `WATER_TABLE` — Altura de la lámina de agua
- `PULSOS` — Pulsos crudos del sensor

### Proveedores de Telemetría Soportados
- **TWIN (TDATA)** — TwinDimension / TDATA
- **Nettra (TheThings.io)** — TheThings Network v2
- **Novus** — Novus Cloud
- **Tago.io** — TagoIO
- **Generic JSON** — Configurable vía admin (URL, auth, parser JSON)

### Compliance Regulatorio
- **DGA** — Dirección General de Aguas (MOP). Envío cada 3 min con retry persistente y backoff exponencial.
- **SMA** — Superintendencia del Medio Ambiente. Envío cada 5 min (múltiplos de 5).
