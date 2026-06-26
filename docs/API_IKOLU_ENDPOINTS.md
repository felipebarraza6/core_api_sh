# API Ikolu — Endpoints Completos (`/api/ik/`)

> **Auditoría:** 2026-06-03
> **Estado:** Producción activa
> **Base URL:** `https://api.smarthydro.app/api/ik/`
> **Filtrado por usuario:** Todos los endpoints autenticados respetan `owner_user` / `users_viewers`. Staff ve todo.

---

## Tabla Maestra de Endpoints

| # | Endpoint | Método | Auth | Throttle | ¿Por usuario? | Descripción detallada |
|---|----------|--------|------|----------|---------------|----------------------|
| 1 | `/api/ik/login/` | POST | Público | `LoginRateThrottle` | N/A | Login optimizado. Retorna token + user minimal + `points_summary` (total, owned_ids, viewed_ids). Reemplaza al login legacy que devolvía perfil completo con todos los datos anidados. |
| 2 | `/api/ik/points_summary/` | GET | Token | `SummaryRateThrottle` | ✅ Sí | **Pantalla principal del Centro de Control.** Retorna TODOS los puntos del usuario con: última telemetría (flow, total, nivel, water_table, variable_values), estado activo/inactivo, conteo de alertas (legacy + nuevo subsistema), config DGA, provider, proyecto y cliente. Soporta `?limit` y `?offset` para paginación opcional. |
| 3 | `/api/ik/point/<id>/summary/` | GET | Token | `SummaryRateThrottle` | ✅ Sí | **Detalle de un punto específico.** Similar a `points_summary` pero para un solo punto. Incluye última telemetría, esquemas, variables, config DGA, y conteo de alertas. Devuelve 404 si el usuario no es owner ni viewer del punto. |
| 4 | `/api/ik/my_points/` | GET | Token | — | ✅ Sí | **Dropdown/select liviano.** Retorna id, título, proyecto, cliente, frecuencia, telemetry flag, DGA compliance, owner/viewer. Útil para selects, filtros, o cuando no necesitas toda la telemetría. Soporta `?limit`. |
| 5 | `/api/ik/dashboard_stats/` | GET | Token | `DashboardRateThrottle` | ✅ Sí | **KPIs del Centro de Control.** Retorna métricas agregadas: total de puntos, conectados/desconectados hoy, últimos 7 días con consumo/caudal/nivel por punto, warnings (resets/system events), reglas de alerta activas, chat quota. |
| 5a | `/api/ik/control_center/list/` | GET | Token | `DashboardRateThrottle` | ✅ Sí | **Lista paginada de puntos para un día.** Retorna métricas del día, estado, variables y `warnings_count`. Query: `?date=YYYY-MM-DD`, `?project_id`, `?order_by=consumption/-consumption/avg_flow/-avg_flow/avg_level/-avg_level/warnings_count_desc/warnings_count_asc`, `?page`, `?page_size`. |
| 6 | `/api/ik/point/<id>/calendar/` | GET | Token | — | ✅ Sí | **Histórico de consumo por día.** Retorna los últimos N días (`?days`, default 7, max 30) de un punto con: fecha, total acumulado, caudal promedio/máx, nivel promedio, consumo del día, registros por día. Útil para gráficos de barras de consumo diario. |
| 7 | `/api/ik/point/<id>/variables/` | GET | Token | `SummaryRateThrottle` | ✅ Sí | **Mapeo de variables del punto.** Retorna la lista de variables configuradas en los esquemas del punto (id, str_variable, label, type_variable, display_key, min_value, max_value). El cliente usa esto para interpretar el payload dinámico de `variable_values` en la telemetría. |
| 8 | `/api/ik/point/<id>/records/` | GET | Token | — | ✅ Sí | **Registros de telemetría por rango.** Devuelve campos esenciales + `total_raw` (sin addition). Query: `?start=&end=`. Límites: máx 31 días, máx 500 registros. |
| 9 | `/api/ik/point/<id>/config/` (`/api/ik/points/<id>/config/`) | GET/PATCH | Token | `DashboardRateThrottle` | ✅ Sí | **Config del punto.** GET retorna d1-d6, addition, is_telemetry, offset nivel y límites de procesamiento. PATCH actualiza esos campos (solo owner o staff); body JSON parcial. Alias plural disponible. |
| 10 | `/api/ik/compliance/` | GET | Token | `DashboardRateThrottle` | ✅ Sí | **Compliance DGA/SMA.** Por defecto lista los puntos accesibles que tienen compliance **configurado** (código DGA o SMA), activo o inactivo. Filtros: `?active_only=true` (solo activos), `?standard=MAYOR` o `?standard=MAYOR,MEDIO`, `?type_dga=SUPERFICIAL` o `?type_dga=SUPERFICIAL,SUBTERRANEO`, `?search` (nombre o código DGA/SMA), `?project_id`. Orden: `order_by=default` (activos primero, luego % consumido desc), `pct_consumed_desc/asc`, `point_name_asc/desc`, `exceedances_desc`, `near_limit_desc`. Paginación `?page`/`?page_size`. |
| 10a | `/api/ik/compliance/<point_id>/flow_history/` | GET | Token | `DashboardRateThrottle` | ✅ Sí | **Detalle de excedencias de caudal.** Registros con `flow > caudal_autorizado` en los últimos `?days=90` (max 365). Paginado (`?page`, `?page_size`). |
| 10b | `/api/ik/compliance/<point_id>/near_limit/` | GET | Token | `DashboardRateThrottle` | ✅ Sí | **Detalle de mediciones cercanas al límite.** Registros entre el 90% y 100% del caudal autorizado en los últimos `?days=90` (max 365). Paginado. |
| 10c | `/api/ik/control_center/system_events/` | GET | Token | `DashboardRateThrottle` | ✅ Sí | **Listado paginado de eventos del sistema.** Filtra por puntos accesibles. Query: `?point_id`, `?event_type`, `?severity`, `?start`, `?end`, `?search`, `?page`, `?page_size`. |
| 10d | `/api/ik/control_center/system_events/<point_id>/` | GET | Token | `DashboardRateThrottle` | ✅ Sí | **Vista detallada de eventos de un punto.** Mismos filtros y paginación que 10c, pero fijando el punto en la URL. Incluye `point` en la respuesta. |
| 11 | `/api/ik/batch/telemetry/` | POST | Token | `BatchRateThrottle` | ✅ Sí | **Telemetría multi-punto.** Body: `{"point_ids": [1,2,3], "hours": 24}`. Valida que el usuario sea owner/viewer de cada punto. Útil para dashboards que muestran varios puntos a la vez. |
| 12 | `/api/ik/batch/stats/` | POST | Token | `BatchRateThrottle` | ✅ Sí | **Stats agregados multi-punto.** Body: `{"point_ids": [1,2,3], "days": 30}`. Retorna consumo total, conteo de registros, último registro por punto. |
| 13 | `/api/ik/point/<id>/gaps/` | GET | Token | — | ✅ Sí (staff amplía) | **Gap detection.** Muestra huecos de telemetría sin modificar BD. Query opcional: `?start=YYYY-MM-DDTHH:MM:SS&end=YYYY-MM-DDTHH:MM:SS`. Si no se pasan, detecta entre primer y último registro. |
| 14 | `/api/ik/telemetry/backfill/` | POST | Token | `BackfillRateThrottle` | ✅ Sí (staff amplía) | **Re-sync histórico completo.** Ingesta datos del provider (TWIN/NOVUS) para un rango y aplica procesamiento unificado: caudal L/s, nivel+offset, totales en cascada, diffs. Rango máximo 30 días. Body: `{"point_id": 85, "start": "2026-05-01T00:00:00", "end": "2026-05-31T23:00:00"}` |
| 15 | `/api/ik/tickets/` | GET/POST | Token | `TicketRateThrottle` | ✅ Sí | **Listar/crear tickets de soporte.** GET retorna tickets donde el usuario es creador, asignado, o el punto es de su propiedad. Filtros: `status`, `origin`, `category`, `priority`, `assigned_to`, `point`, `search`. POST crea ticket vinculado a un punto. |
| 16 | `/api/ik/tickets/<id>/` | GET/PATCH | Token | `TicketRateThrottle` | ✅ Sí | **Ver/actualizar ticket.** PATCH permite cambiar título/descripción/prioridad/categoría (cliente). Staff puede todo. |
| 17 | `/api/ik/tickets/<id>/comments/` | GET/POST | Token | `TicketRateThrottle` | ✅ Sí | **Comentarios.** Los internos (`is_internal=true`) solo los ve staff. POST marca SLA responded al primer comentario de staff. |
| 18 | `/api/ik/tickets/<id>/assign/` | POST | Token | `TicketRateThrottle` | Staff only | **Asignar ticket.** Solo staff puede reasignar. Valida que el usuario destino exista. |
| 19 | `/api/ik/tickets/<id>/status/` | POST | Token | `TicketRateThrottle` | ✅ Sí | **Cambiar estado.** Creador puede marcar RESUELTO. Staff puede cualquier estado. Registra en activity log. |
| 20 | `/api/ik/tickets/<id>/attachments/` | GET/POST | Token | `TicketRateThrottle` | ✅ Sí | **Adjuntos.** Validación de extensión y tamaño (max 10 MB). |
| 21 | `/api/ik/tickets/stats/` | GET | Token | `TicketRateThrottle` | ✅ Sí | **Métricas de soporte.** Total, por estado, categoría, prioridad, origen, SLA vencidos. |
| 22 | `/api/ik/announcements/public/` | GET | Público | `PublicReadRateThrottle` | N/A | **Anuncios del sistema sin login.** Mantenimientos, novedades. |
| 23 | `/api/ik/auth/password-reset/` | POST | Público | — | N/A | Solicitar reset de contraseña. Envía email con token temporal. |
| 24 | `/api/ik/auth/password-reset/confirm/` | POST | Público | — | N/A | Confirmar reset con token. |
| 25 | `/api/ik/auth/password-reset/validate/` | POST | Público | — | N/A | Validar token de reset sin cambiar password. |
| 26 | `/api/ik/chat/client/general_stats/` | POST | Token | `DashboardRateThrottle` | ✅ Sí | **Chat interpretativo con Gemini.** Backend inyecta stats del dashboard como contexto. Body: `{"message": "..."}`. Límite: 12 preguntas diarias por usuario. |
| 27 | `/api/ik/system-events/summary/` | GET | Token | `DashboardRateThrottle` | ✅ Sí | **Resumen de eventos del sistema.** Conteos por severidad, tipo, punto, timeline. Query: `?days=7&point_id=` |

---

## Detalle de Payloads y Responses

### Login (`POST /api/ik/login/`)

**Request:**
```json
{
  "email": "usuario@ejemplo.com",
  "password": "secreto123"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Login exitoso",
  "access_token": "abc123...",
  "user": {
    "id": 1,
    "email": "usuario@ejemplo.com",
    "first_name": "Juan",
    "last_name": "Pérez",
    "is_staff": false,
    "is_client_admin": false
  },
  "points_summary": {
    "total": 5,
    "owned_ids": [1, 2, 3],
    "viewed_ids": [4, 5]
  }
}
```

---

### Points Summary (`GET /api/ik/points_summary/`)

**Query params:** `?limit=20&offset=0`

**Response (item de array):**
```json
{
  "id": 1,
  "title": "Pozo Norte",
  "project": { "id": 1, "title": "Proyecto A", "client": { "id": 1, "name": "Cliente X" } },
  "frequency_minutes": 5,
  "is_telemetry_active": true,
  "provider": { "id": 1, "name": "TWIN", "handler": "tdata" },
  "last_interaction": {
    "date_time_medition": "2026-06-03T12:00:00Z",
    "flow": 45.2,
    "total": 12500.50,
    "nivel": 12.3,
    "water_table": 8.5,
    "variable_values": { "d1": 100, "d2": 200 }
  },
  "alerts_count": 2,
  "dga_config": { "send_dga": true, "standard": "MAYOR", "code": "123-45" },
  "is_owner": true,
  "is_viewer": false
}
```

---

### Dashboard Stats (`GET /api/ik/dashboard_stats/`)

**Response:**
```json
{
  "total_points": 10,
  "active_points": 8,
  "disconnected_today": 2,
  "points_with_alerts": 1,
  "last_7_days": [
    {
      "point_id": 1,
      "point_title": "Pozo Norte",
      "daily_consumption": [120.5, 115.0, 130.2, ...],
      "avg_flow": 42.3,
      "max_flow": 55.1,
      "avg_nivel": 12.1,
      "total_records": 288
    }
  ],
  "warnings": {
    "resets_today": 0,
    "system_events_24h": 1
  },
  "chat_quota": {
    "daily_limit": 12,
    "used_today": 3,
    "remaining": 9
  }
}
```

---

### Batch Telemetry (`POST /api/ik/batch/telemetry/`)

**Request:**
```json
{
  "point_ids": [1, 2, 3],
  "hours": 24
}
```

**Response:**
```json
{
  "results": {
    "1": {
      "point": { "id": 1, "title": "Pozo Norte" },
      "latest_record": { /* InteractionDetail esencial */ },
      "records_count": 288
    },
    "2": { ... },
    "3": { ... }
  },
  "errors": {}
}
```

---

### Batch Stats (`POST /api/ik/batch/stats/`)

**Request:**
```json
{
  "point_ids": [1, 2, 3],
  "days": 30
}
```

**Response:**
```json
{
  "results": {
    "1": {
      "point": { "id": 1, "title": "Pozo Norte" },
      "total_consumption": 3500.5,
      "records_count": 8640,
      "last_record_at": "2026-06-03T12:00:00Z"
    }
  }
}
```

---

### Calendar (`GET /api/ik/point/<id>/calendar/?days=7`)

**Response:**
```json
{
  "point_id": 1,
  "days": 7,
  "data": [
    {
      "date": "2026-06-03",
      "total": 12500.50,
      "avg_flow": 42.3,
      "max_flow": 55.1,
      "avg_nivel": 12.1,
      "consumption": 120.5,
      "records_count": 288
    }
  ]
}
```

---

### Records (`GET /api/ik/point/<id>/records/?start=2026-06-01T00:00:00&end=2026-06-03T23:59:59`)

**Response:**
```json
{
  "point_id": 1,
  "count": 500,
  "records": [
    {
      "id": 12345,
      "date_time_medition": "2026-06-03T12:00:00Z",
      "date_time_last_logger": "2026-06-03T11:59:00Z",
      "flow": 45.2,
      "total": 12500.50,
      "total_raw": 12400.50,
      "nivel": 12.3,
      "water_table": 8.5,
      "pulses": 100,
      "is_partial": false,
      "send_dga": true,
      "is_error": false
    }
  ]
}
```

---

### Point Config (`GET/PATCH /api/ik/point/<id>/config/`)

**GET Response:**
```json
{
  "d1": "1.00",
  "d2": "2.00",
  "d3": "3.00",
  "d4": "4.00",
  "d5": "5.00",
  "d6": 10,
  "addition": "100.000",
  "is_telemetry": true,
  "nivel_offset": "-17.000",
  "max_diff_m3_per_hour": "600.00",
  "max_flow_ls": "200.00",
  "max_time_gap_hours": "3.00",
  "reconnection_threshold_hours": "2.50",
  "replicate_on_missing": false,
  "use_transaction_atomic": true
}
```

**PATCH Request:**
```json
{
  "d1": "9.50",
  "d6": 42,
  "is_telemetry": false,
  "max_flow_ls": "99.99"
}
```

Campos editables: `d1`-`d6`, `addition`, `is_telemetry`, `nivel_offset`, `max_diff_m3_per_hour`, `max_flow_ls`, `max_time_gap_hours`, `reconnection_threshold_hours`, `replicate_on_missing`, `use_transaction_atomic`.

- Solo el **owner** del punto o **staff/superuser** pueden editar.
- Viewers solo lectura.
- Campos desconocidos o tipos inválidos retornan 400.

### Compliance (`GET /api/ik/compliance/`)

**Query params:**
- `?active_only=true` — solo puntos con compliance activo (default `false`, muestra configurados activos o inactivos).
- `?standard=<estandar>` — filtrar por estándar. Soporta múltiples separados por coma: `?standard=MAYOR,MEDIO`. Opciones: `SIN_ESTANDAR`, `MAYOR`, `MEDIO`, `MENOR`, `CAUDALES_MUY_PEQUENOS`.
- `?project_id=<id>` — filtrar por proyecto.
- `?search=<texto>` — filtrar por nombre de punto **o código DGA/SMA** (`icontains`). Ej: `?search=OB-0702` o `?search=0702`.
- `?order_by=default|pct_consumed_desc|pct_consumed_asc|point_name_asc|point_name_desc|exceedances_desc|near_limit_desc`. Siempre activos primero; luego el criterio elegido.
- `?page=<n>&page_size=<n>` (default 10, max 100).

**Response:**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "points": [
    {
      "point_id": 1,
      "project_id": 3,
      "point_name": "Pozo Norte",
      "client_name": "Cliente A",
      "code": "123-45",
      "compliance_type": ["DGA"],
      "standard": "MAYOR",
      "type_dga": "SUPERFICIAL",
      "compliance_active": true,
      "authorized_flow": 100.0,
      "authorized_total": 50000.0,
      "annual_consumption": 45000.0,
      "pct_consumed": 90.0,
      "flow": 95.0,
      "water_table": 0.0,
      "flow_history": { "count": 5, "has_more": false, "threshold": 100.0 },
      "near_limit_history": { "count": 8, "has_more": false, "threshold": 100.0 },
      "compliance_warning": { "level": "warning" },
      "voucher": "V123456"
    },
    {
      "point_id": 2,
      "project_id": 3,
      "point_name": "Canal Sur",
      "client_name": "Cliente A",
      "code": null,
      "compliance_type": [],
      "standard": null,
      "type_dga": null,
      "compliance_active": false,
      "authorized_flow": null,
      "authorized_total": null,
      "annual_consumption": 0.0,
      "pct_consumed": null,
      "flow": 12.0,
      "water_table": 0.0,
      "flow_history": { "count": 0, "has_more": false, "threshold": null },
      "near_limit_history": { "count": 0, "has_more": false, "threshold": null },
      "compliance_warning": { "level": "unknown" },
      "voucher": null
    }
  ]
}
```

- `flow_history.count` / `near_limit_history.count` son conteos reales (sin límite de 20).
- `has_more` indica si al abrir el modal conviene paginar por el endpoint de detalle.

### Compliance flow history detail (`GET /api/ik/compliance/<point_id>/flow_history/`)

```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "threshold": 100.0,
  "point_id": 1,
  "results": [
    { "date_time": "2026-06-03T14:00:00", "flow": 120.0 }
  ]
}
```

### Compliance near limit detail (`GET /api/ik/compliance/<point_id>/near_limit/`)

```json
{
  "count": 8,
  "next": null,
  "previous": null,
  "threshold": 100.0,
  "point_id": 1,
  "results": [
    { "date_time": "2026-06-03T13:00:00", "flow": 95.0 }
  ]
}
```

---

### Control Center System Events (`GET /api/ik/control_center/system_events/`)

**Query params:**
- `point_id` — filtrar por punto (valida acceso del usuario).
- `event_type` — `DISCONNECTION`, `RECONNECTION`, `COUNTER_RESET`, `API_ERROR`, `THRESHOLD_ALERT`, `GENERAL`.
- `severity` — `INFO`, `WARNING`, `CRITICAL`.
- `start` / `end` — rango ISO, ej. `2026-06-01T00:00:00` / `2026-06-30T23:59:59`.
- `search` — búsqueda `icontains` en `title` o `message`.
- `page` / `page_size` — paginación.

**Response:**
```json
{
  "count": 42,
  "next": "?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "event_type": "DISCONNECTION",
      "severity": "WARNING",
      "title": "Punto desconectado",
      "message": "Punto desconectado por más de 24h",
      "point": { "id": 1, "name": "Pozo Norte" },
      "created": "2026-06-03T10:00:00Z"
    }
  ]
}
```

- Staff y superusuarios ven eventos de todos los puntos.
- Usuarios regulares solo ven eventos de puntos donde son owner o viewer.

### System Events Summary (`GET /api/ik/system-events/summary/?days=7`)

**Response:**
```json
{
  "days": 7,
  "total_events": 15,
  "by_severity": {
    "INFO": 10,
    "WARNING": 3,
    "CRITICAL": 2
  },
  "by_type": {
    "COUNTER_RESET": 2,
    "DISCONNECTION": 3,
    "RECONNECTION": 3,
    "API_ERROR": 7
  },
  "by_point": {
    "1": 5,
    "2": 10
  },
  "timeline": [
    { "date": "2026-06-03", "count": 3 }
  ],
  "recent_events": [
    {
      "id": 1,
      "event_type": "DISCONNECTION",
      "severity": "WARNING",
      "message": "Punto desconectado por 24h",
      "catchment_point": 1,
      "created_at": "2026-06-03T10:00:00Z"
    }
  ]
}
```

---

### Tickets Stats (`GET /api/ik/tickets/stats/`)

**Response:**
```json
{
  "total_tickets": 20,
  "by_status": {
    "ABIERTO": 5,
    "EN_ANALISIS": 3,
    "ESPERA_CLIENTE": 2,
    "RESUELTO": 8,
    "CERRADO": 2
  },
  "by_category": {
    "TELEMETRIA": 8,
    "SOFTWARE": 5,
    "CONECTIVIDAD": 4,
    "DGA": 2,
    "HARDWARE": 1
  },
  "by_priority": {
    "BAJA": 5,
    "MEDIA": 10,
    "ALTA": 4,
    "CRITICA": 1
  },
  "sla": {
    "responded_on_time": 18,
    "resolved_on_time": 15,
    "overdue_response": 2,
    "overdue_resolution": 3
  }
}
```

---

## Endpoints Legacy que siguen activos (`/api/`)

| Endpoint | Estado | ¿Quién lo usa? |
|----------|--------|----------------|
| `/api/catchment_points/` | ✅ Activo | Web app legacy (admin Django + frontend web) |
| `/api/interaction_detail/` | ✅ Activo | Web app legacy — CRUD + export XLS |
| `/api/interaction_detail_json/` | ✅ Activo | Web app legacy — CRUD telemetría JSON |
| `/api/management/points_status/` | ✅ Activo | Web app legacy — monitoreo en tiempo real |
| `/api/management/system_status/` | ✅ Activo | Dashboard admin |
| `/api/reports/*` | ✅ Activo | Web app legacy — reportes Excel/JSON |
| `/api/users/` | ✅ Activo | Web app legacy — gestión de usuarios |
| `/api/notifications_catchment/` | ⚠️ Legacy | Web app — sistema viejo de notificaciones, siendo reemplazado por tickets + AlertRule |
| `/api/response_notifications_catchment/` | ⚠️ Legacy | Web app — respuestas a notificaciones legacy. Sincronizado con AlertTrigger para alertas umbral. |
| `/api/alert_rules/` | ✅ Activo | Nuevo subsistema de alertas |
| `/api/system_events/` | ✅ Activo | Eventos del sistema (reemplaza notificaciones de desconexión/reconexión/error) |

---

## Flujo recomendado para el Centro de Control

```
1. LOGIN
   POST /api/ik/login/
   → Guardar token

2. DASHBOARD PRINCIPAL
   GET /api/ik/dashboard_stats/
   GET /api/ik/points_summary/?limit=20
   → Mostrar KPIs + lista de puntos

3. DETALLE DE PUNTO
   GET /api/ik/point/<id>/summary/
   GET /api/ik/point/<id>/calendar/?days=30
   GET /api/ik/point/<id>/variables/
   → Tabs: Resumen / Calendario / Variables

4. TELEMETRÍA CRUDA
   GET /api/ik/point/<id>/records/?start=...&end=...
   → Gráfico de serie temporal

5. COMPARACIÓN MULTI-PUNTO
   POST /api/ik/batch/stats/
   → Gráfico comparativo

6. COMPLIANCE
   GET /api/ik/compliance/
   → Tabla de cumplimiento regulatorio

7. SOPORTE
   GET /api/ik/tickets/
   POST /api/ik/tickets/ (crear)
   GET /api/ik/tickets/<id>/comments/

8. CHAT IA
   POST /api/ik/chat/client/general_stats/
   → Asistente interpretativo
```

---

## Throttling Detallado

| Clase | Rate | ¿A quién afecta? |
|-------|------|------------------|
| `AnonRateThrottle` | 100/h | Login legacy |
| `LoginRateThrottle` | 100/h | `/api/ik/login/` |
| `BatchRateThrottle` | 10/min | Batch telemetry + stats |
| `SummaryRateThrottle` | 60/min | Points summary, point summary, variables, my_points |
| `DashboardRateThrottle` | 30/min | Dashboard, compliance, chat client, system events |
| `PublicReadRateThrottle` | 100/h | Anuncios públicos |
| `TicketRateThrottle` | 60/min | Todo el namespace `/api/ik/tickets/` |
| `BackfillRateThrottle` | 5/min | Backfill telemetry |
