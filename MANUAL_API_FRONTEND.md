# 📘 MANUAL COMPLETO DE LA API - SmartHydro

> **Para el equipo Frontend** — Copia y pega los ejemplos directamente.
> **Base URL:** `https://tu-dominio.com` (ajustar según entorno)

---

## 🔐 AUTENTICACIÓN

La API usa **Token Authentication** de Django REST Framework.

- En TODAS las peticiones protegidas, enviar header:
```
Authorization: Bearer <tu_token>
```
> El token se obtiene en el login. También viene en el header `Authorization` de la respuesta.

---

## 🌐 ENDPOINTS PÚBLICOS (Sin Auth)

### `GET /`
Info básica del servicio.

**Ejemplo:**
```bash
curl -X GET "https://tu-dominio.com/"
```

**Respuesta:**
```json
{
  "service": "SmartHydro API",
  "version": "1.0",
  "status": "operational",
  "endpoints": {
    "legacy_api": "/api/",
    "optimized_api": "/api/ik/",
    "admin": "/admin/",
    "health": "/health/"
  },
  "timestamp": "2026-05-08T04:00:00Z"
}
```

---

### `GET /health/`
Health check para monitoreo.

**Ejemplo:**
```bash
curl -X GET "https://tu-dominio.com/health/"
```

**Respuesta:**
```json
{
  "status": "ok",
  "service": "SmartHydro API",
  "timestamp": "2026-05-08T04:00:00Z"
}
```

---

### `GET /status/`
Estado del sistema en JSON (DB, cache, cronjobs).

**Ejemplo:**
```bash
curl -X GET "https://tu-dominio.com/status/"
```

**Respuesta:**
```json
{
  "status": "operational",
  "timestamp": "2026-05-08T04:00:00Z",
  "response_time_ms": 45.23,
  "services": {
    "api": { "status": "operational", "name": "SmartHydro API" },
    "database": { "status": "operational", "name": "PostgreSQL", "connections": 12 },
    "cache": { "status": "operational", "name": "Redis Cache" },
    "cronjobs": { "status": "operational", "name": "Cronjobs", "active": true }
  },
  "statistics": {
    "total_points": 150,
    "active_points": 148,
    "records_24h": 12500,
    "dga_queue": 340
  }
}
```

---

### `GET /status/dashboard/`
Dashboard HTML de estado (renderiza template, no JSON).

---

## 👤 1. USUARIOS — `/api/users/`

> **Auth requerida** excepto `login` y `signup`.

### CRUD Estándar (ViewSet con DefaultRouter)

| Método | URL | Qué hace |
|--------|-----|----------|
| `GET` | `/api/users/` | Listar usuarios verificados |
| `POST` | `/api/users/` | Crear usuario |
| `GET` | `/api/users/{username}/` | Obtener usuario por username |
| `PUT` | `/api/users/{username}/` | Actualizar usuario completo |
| `PATCH` | `/api/users/{username}/` | Actualizar parcial |
| `DELETE` | `/api/users/{username}/` | Eliminar usuario |

**Filtros disponibles:** vía `?campo=valor` (DjangoFilterBackend activado).

---

### `POST /api/users/login/`
Login de usuario. Devuelve token y datos del usuario con sus puntos de captación.

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "email": "usuario@ejemplo.com",
  "password": "tu_password"
}
```

**Ejemplo cURL:**
```bash
curl -X POST "https://tu-dominio.com/api/users/login/" \
  -H "Content-Type: application/json" \
  -d '{"email":"usuario@ejemplo.com","password":"tu_password"}'
```

**Respuesta 200:**
```json
{
  "success": true,
  "message": "Login exitoso",
  "user": {
    "id": 1,
    "username": "juanperez",
    "first_name": "Juan",
    "last_name": "Perez",
    "email": "usuario@ejemplo.com",
    "catchment_points": [ /* Array completo de puntos con config, DGA, módulos */ ]
  },
  "access_token": "a1b2c3d4e5f6..."
}
```
> **Nota:** El header `Authorization: Bearer <token>` también viene en la respuesta.

---

### `POST /api/users/signup/`
Registro de nuevo usuario.

**Body:**
```json
{
  "email": "nuevo@ejemplo.com",
  "username": "nuevouser",
  "password": "password123",
  "password_confirmation": "password123"
}
```

**Ejemplo cURL:**
```bash
curl -X POST "https://tu-dominio.com/api/users/signup/" \
  -H "Content-Type: application/json" \
  -d '{"email":"nuevo@ejemplo.com","username":"nuevouser","password":"password123","password_confirmation":"password123"}'
```

---

## 📊 2. TELEMETRÍA — `/api/interaction_detail_json/`

> **Auth:** `Bearer <token>` requerido.

### CRUD principal de telemetría

| Método | URL | Qué hace |
|--------|-----|----------|
| `GET` | `/api/interaction_detail_json/` | Listar registros de telemetría (paginado) |
| `POST` | `/api/interaction_detail_json/` | Crear registro de telemetría |
| `GET` | `/api/interaction_detail_json/{id}/` | Obtener registro por ID |
| `PUT` | `/api/interaction_detail_json/{id}/` | Actualizar registro completo |
| `PATCH` | `/api/interaction_detail_json/{id}/` | Actualizar parcial |
| `DELETE` | `/api/interaction_detail_json/{id}/` | Eliminar registro |

**Filtros disponibles (query params):**
| Filtro | Ejemplo | Descripción |
|--------|---------|-------------|
| `catchment_point` | `?catchment_point=42` | Filtrar por punto de captación (exact) |
| `send_dga` | `?send_dga=true` | En cola DGA (exact) |
| `date_time_medition__gte` | `?date_time_medition__gte=2026-01-01` | Fecha medición >= |
| `date_time_medition__lte` | `?date_time_medition__lte=2026-01-31` | Fecha medición <= |
| `date_time_medition__year` | `?date_time_medition__year=2026` | Año exacto |
| `date_time_medition__month` | `?date_time_medition__month=5` | Mes exacto |
| `date_time_medition__day` | `?date_time_medition__day=8` | Día exacto |
| `date_time_medition__date__range` | `?date_time_medition__date__range=2026-01-01,2026-01-31` | Rango de fechas |
| `hour` | `?hour=14` | Hora exacta (0-23) |
| `created` | (mismos lookups que date_time_medition) | Por fecha de creación |

**Paginación:** La respuesta usa paginación DRF por defecto:
```json
{
  "count": 1000,
  "next": "https://tu-dominio.com/api/interaction_detail_json/?page=2",
  "previous": null,
  "results": [ /* registros */ ]
}
```

> **⚠️ Importante:** Si no se especifica filtro de fecha, limita a **100 registros** por defecto. Si el punto tiene frecuencia `1` o `5` minutos, limita a **50 registros**.

**Campos del modelo InteractionDetail:**
```json
{
  "id": 1,
  "date_time_medition": "2026-05-08T04:00:00Z",
  "date_time_last_logger": "2026-05-08T03:55:00Z",
  "flow": 12.5,
  "total": 150000,
  "total_diff": 2.3,
  "total_today_diff": 45.6,
  "nivel": 3.2,
  "water_table": 2.8,
  "pulses": 120,
  "send_dga": true,
  "return_dga": null,
  "n_voucher": "ABC123",
  "is_error": false,
  "is_partial": false,
  "days_not_conection": 0,
  "notification": null,
  "catchment_point": 42,
  "created": "2026-05-08T04:00:00Z",
  "modified": "2026-05-08T04:00:00Z"
}
```

**Ejemplo cURL listado:**
```bash
curl -X GET "https://tu-dominio.com/api/interaction_detail_json/?catchment_point=42&date_time_medition__date__range=2026-05-01,2026-05-08" \
  -H "Authorization: Bearer TU_TOKEN"
```

---

## 📋 3. TELEMETRÍA OVERRIDE (Sin paginación)

> **Auth:** `Bearer <token>` requerido.

### `GET/POST/PUT/PATCH/DELETE /api/interaction_detail_override/`
Igual que `interaction_detail_json` pero **sin paginación**. Útil para descargar todos los datos filtrados.

### `GET/POST/PUT/PATCH/DELETE /api/interaction_detail_override_month/`
Igual que override pero retorna **solo el último registro por día** para cada punto.

### `GET /api/interaction_detail_override_month_xlsx/`
Devuelve Excel `.xlsx` con último registro por día.

**Headers para descargar Excel:**
```
Accept: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
```

---

## 📈 4. EXPORTACIONES EXCEL

### `GET /api/interaction_detail/` — Excel telemetría completa
Retorna JSON por defecto. Para forzar Excel, usar header `Accept` de XLSX o agregar `?format=xlsx`.

**Filtros:** `catchment_point`, `send_dga`, `date_time_medition` (mismos lookups).

### `GET /api/interaction_detail_dga/` — Excel formato DGA
Mismo funcionamiento pero formato optimizado para reportes DGA.

### `GET /reports/active-points/` — Reporte de puntos activos
Devuelve un `.xlsx` con puntos que tienen telemetría activa.

**Auth:** Session o Basic Auth.

**Ejemplo:**
```bash
curl -X GET "https://tu-dominio.com/reports/active-points/" \
  -u "usuario:password" \
  -H "Accept: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  --output reporte_puntos_activos.xlsx
```

---

## 🏭 5. PUNTOS DE CAPTACIÓN Y CONFIGURACIÓN

> **Auth:** `Bearer <token>` requerido en todos.

Todos son ViewSets con CRUD completo + DjangoFilterBackend.

### Clientes
```
GET    /api/client/
POST   /api/client/
GET    /api/client/{id}/
PUT    /api/client/{id}/
PATCH  /api/client/{id}/
DELETE /api/client/{id}/
```

### Proyectos
```
GET    /api/project_catchments/
POST   /api/project_catchments/
GET    /api/project_catchments/{id}/
PUT    /api/project_catchments/{id}/
PATCH  /api/project_catchments/{id}/
DELETE /api/project_catchments/{id}/
```

### Puntos de Captación
```
GET    /api/catchment_point/
POST   /api/catchment_point/
GET    /api/catchment_point/{id}/
PUT    /api/catchment_point/{id}/
PATCH  /api/catchment_point/{id}/
DELETE /api/catchment_point/{id}/
```

**Comportamiento especial:**
- `list` → usa `CatchmentPointSerializer` (básico)
- `retrieve` → usa `CatchmentPointIkoluSerializer` (incluye `profile_ikolu`, `config_data`, `dga`, `modules`)

**Ejemplo retrieve punto completo:**
```bash
curl -X GET "https://tu-dominio.com/api/catchment_point/42/" \
  -H "Authorization: Bearer TU_TOKEN"
```

**Respuesta retrieve (resumida):**
```json
{
  "id": 42,
  "title": "Punto P-01",
  "frecuency": "60",
  "lat": -33.456,
  "lon": -70.648,
  "profile_ikolu": {
    "entry_by_form": true,
    "m1": "dato1", "m2": "dato2", "m3": "dato3",
    "m4": "dato4", "m5": "dato5", "m6": "dato6"
  },
  "config_data": {
    "d1": 1.0, "d2": 2.0, "d3": 3.0, "d4": 4.0, "d5": 5.0, "d6": 6.0,
    "addition": 0,
    "date_start_telemetry": "2025-01-01",
    "date_delivery_act": "2025-01-15",
    "is_telemetry": true,
    "variables": [ /* array de variables configuradas */ ]
  },
  "dga": {
    "send_dga": true,
    "standard": "RM",
    "type_dga": "MENOR",
    "code_dga": "DG-001",
    "flow_granted_dga": 50.0,
    "total_granted_dga": 10000.0,
    "shac": 500.0,
    "date_start_compliance": "2025-01-01",
    "date_created_code": "2025-01-01"
  },
  "modules": {
    "m1": { /* último registro de telemetría */ },
    "m2": [ /* últimos 48 registros DGA */ ],
    "m22": [ /* últimos 24 registros DGA de hoy */ ],
    "first_data_today": { /* primer registro del día */ },
    "first_actual_year": { /* primer registro del año */ },
    "today": [ /* registros de hoy */ ],
    "yesterday": [ /* registros de ayer */ ],
    "last_data_yesterday": { /* último registro de ayer */ },
    "total_consumed_yesterday": 120.5,
    "total_consumed_today": 85.3,
    "total_consumed_year": 4520.0,
    "files": [ /* archivos asociados */ ],
    "alerts": [ /* alertas del punto */ ]
  }
}
```

---

### Perfiles Ikolu
```
GET    /api/profile_ikolu_catchment/
POST   /api/profile_ikolu_catchment/
GET    /api/profile_ikolu_catchment/{id}/
PUT    /api/profile_ikolu_catchment/{id}/
PATCH  /api/profile_ikolu_catchment/{id}/
DELETE /api/profile_ikolu_catchment/{id}/
```

### Notificaciones
```
GET    /api/notifications_catchment/
POST   /api/notifications_catchment/
GET    /api/notifications_catchment/{id}/
PUT    /api/notifications_catchment/{id}/
PATCH  /api/notifications_catchment/{id}/
DELETE /api/notifications_catchment/{id}/
```

**Filtros disponibles:**
- `point_catchment`, `type_variable`, `type_notification`, `type_alert`
- `is_periodic`, `is_active`, `is_read`, `is_response`, `is_finish`, `is_wait`
- `status_dga`, `status_sma`, `start_date`, `end_date`

**Retrieve** (`GET /api/notifications_catchment/{id}/`) incluye campo extra `stats`:
```json
{
  "stats": {
    "total_triggers": 15,
    "first_trigger": "2026-01-01T00:00:00Z",
    "last_trigger": "2026-05-08T00:00:00Z",
    "triggers_last_24h": 2,
    "triggers_last_7d": 5,
    "triggers_last_30d": 12,
    "active_days": 8,
    "avg_hours_between_triggers": 12.5,
    "peak_hour": { "hour": 14, "count": 5 },
    "last_measured_value": 45.2,
    "trigger_history": [ /* historial de disparos con mediciones cercanas */ ]
  }
}
```

---

### Respuestas a Notificaciones
```
GET    /api/response_notifications_catchment/
POST   /api/response_notifications_catchment/
GET    /api/response_notifications_catchment/{id}/
PUT    /api/response_notifications_catchment/{id}/
PATCH  /api/response_notifications_catchment/{id}/
DELETE /api/response_notifications_catchment/{id}/
```

**Filtros:** `notification`, `user`
**List** usa profundidad (`depth=1`) para mostrar relaciones anidadas.

---

### Tipos de Archivo
```
GET    /api/type_file_catchment/
POST   /api/type_file_catchment/
GET    /api/type_file_catchment/{id}/
PUT    /api/type_file_catchment/{id}/
PATCH  /api/type_file_catchment/{id}/
DELETE /api/type_file_catchment/{id}/
```

### Archivos
```
GET    /api/file_catchment/
POST   /api/file_catchment/
GET    /api/file_catchment/{id}/
PUT    /api/file_catchment/{id}/
PATCH  /api/file_catchment/{id}/
DELETE /api/file_catchment/{id}/
```

### Configuración de Datos
```
GET    /api/profile_data_config_catchment/
POST   /api/profile_data_config_catchment/
GET    /api/profile_data_config_catchment/{id}/
PUT    /api/profile_data_config_catchment/{id}/
PATCH  /api/profile_data_config_catchment/{id}/
DELETE /api/profile_data_config_catchment/{id}/
```

### Configuración DGA
```
GET    /api/dga_data_config_catchment/
POST   /api/dga_data_config_catchment/
GET    /api/dga_data_config_catchment/{id}/
PUT    /api/dga_data_config_catchment/{id}/
PATCH  /api/dga_data_config_catchment/{id}/
DELETE /api/dga_data_config_catchment/{id}/
```

### Esquemas
```
GET    /api/schemes_catchment/
POST   /api/schemes_catchment/
GET    /api/schemes_catchment/{id}/
PUT    /api/schemes_catchment/{id}/
PATCH  /api/schemes_catchment/{id}/
DELETE /api/schemes_catchment/{id}/
```

### Variables
```
GET    /api/variable/
POST   /api/variable/
GET    /api/variable/{id}/
PUT    /api/variable/{id}/
PATCH  /api/variable/{id}/
DELETE /api/variable/{id}/
```

### Personas Registradas
```
GET    /api/register_persons/
POST   /api/register_persons/
GET    /api/register_persons/{id}/
PUT    /api/register_persons/{id}/
PATCH  /api/register_persons/{id}/
DELETE /api/register_persons/{id}/
```

---

## ⚙️ 6. GESTIÓN Y ADMINISTRACIÓN — `/api/management/`

> **Auth:** `Bearer <token>` requerido.

### `GET /api/management/system_status/`
Estado general del sistema.

**Ejemplo:**
```bash
curl -X GET "https://tu-dominio.com/api/management/system_status/" \
  -H "Authorization: Bearer TU_TOKEN"
```

**Respuesta:**
```json
{
  "status": "operational",
  "statistics": {
    "total_points": 150,
    "active_telemetry": 120,
    "inactive_telemetry": 30,
    "disconnected_points": 5,
    "records_last_24h": 12500,
    "active_notifications": 8,
    "dga_queue_size": 340,
    "error_records_24h": 2
  },
  "timestamp": "2026-05-08T04:00:00Z"
}
```

---

### `GET /api/management/points_status/`
Estado detallado de puntos de captación.

**Query params:**
- `project` — Filtrar por proyecto ID
- `client` — Filtrar por cliente ID
- `disconnected=true` — Solo puntos desconectados
- `active_telemetry=true` — Solo con telemetría activa

**Ejemplo:**
```bash
curl -X GET "https://tu-dominio.com/api/management/points_status/?project=5&disconnected=true" \
  -H "Authorization: Bearer TU_TOKEN"
```

**Respuesta:**
```json
{
  "points": [
    {
      "id": 42,
      "title": "Punto P-01",
      "project": "Proyecto Alpha",
      "client": "Cliente Beta",
      "frecuency": "60",
      "provider": { "twin": false, "nettra": true, "novus": false },
      "telemetry_active": true,
      "last_interaction": {
        "date_time": "2026-05-08T03:00:00Z",
        "days_not_connection": 0,
        "flow": 12.5,
        "total": 150000,
        "nivel": 3.2,
        "is_error": false
      }
    }
  ],
  "total": 1,
  "timestamp": "2026-05-08T04:00:00Z"
}
```

---

### `GET /api/management/telemetry_metrics/`
Métricas agregadas de telemetría.

**Query params:**
- `point` — ID del punto (opcional)
- `days` — Días a consultar (default: 7)

**Ejemplo:**
```bash
curl -X GET "https://tu-dominio.com/api/management/telemetry_metrics/?point=42&days=7" \
  -H "Authorization: Bearer TU_TOKEN"
```

**Respuesta:**
```json
{
  "metrics": {
    "total_records": 168,
    "avg_flow": 11.2,
    "max_flow": 25.4,
    "min_flow": 0.0,
    "total_consumption": 850.5,
    "avg_nivel": 3.1,
    "error_count": 0,
    "error_percentage": 0.0
  },
  "daily_records": [
    { "date": "2026-05-01", "count": 24 },
    { "date": "2026-05-02", "count": 24 }
  ],
  "hourly_records": [
    { "hour": "2026-05-08T00:00:00Z", "count": 4 }
  ],
  "period": {
    "start_date": "2026-05-01T04:00:00Z",
    "end_date": "2026-05-08T04:00:00Z",
    "days": 7
  },
  "timestamp": "2026-05-08T04:00:00Z"
}
```

---

### `POST /api/management/toggle_telemetry/`
Activar/desactivar telemetría de un punto.

**Body:**
```json
{
  "point_id": 42,
  "enabled": false
}
```

**Ejemplo:**
```bash
curl -X POST "https://tu-dominio.com/api/management/toggle_telemetry/" \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"point_id":42,"enabled":false}'
```

---

### `GET /api/management/dga_queue_status/`
Estado de la cola DGA.

**Ejemplo:**
```bash
curl -X GET "https://tu-dominio.com/api/management/dga_queue_status/" \
  -H "Authorization: Bearer TU_TOKEN"
```

**Respuesta:**
```json
{
  "queue_status": {
    "total": 340,
    "errors": 2,
    "old_records": 15
  },
  "by_point": [
    { "catchment_point__title": "Punto P-01", "catchment_point__id": 42, "count": 50 }
  ],
  "timestamp": "2026-05-08T04:00:00Z"
}
```

---

### `POST /api/management/clear_dga_queue/`
Limpiar cola DGA.

**Body (opcional):**
```json
{
  "point_id": 42,
  "only_errors": true
}
```

---

### `POST /api/management/requeue_dga/`
Reagregar registros a la cola DGA.

**Body (opcional):**
```json
{
  "point_id": 42,
  "start_date": "2026-01-01",
  "end_date": "2026-05-08",
  "only_errors": false
}
```

---

### `POST /api/management/update_point_frequency/`
Cambiar frecuencia de un punto.

**Body:**
```json
{
  "point_id": 42,
  "frequency": "5"
}
```
> Valores permitidos: `1`, `5`, `10`, `60` (minutos)

---

### `GET /api/management/notifications_summary/`
Resumen de notificaciones.

**Query params:**
- `days` — Días a consultar (default: 7)

**Respuesta:**
```json
{
  "summary": {
    "total": 25,
    "active": 5,
    "unread": 3,
    "finished": 20
  },
  "by_type": [
    { "type_notification": "ALERT", "count": 15 },
    { "type_notification": "WARNING", "count": 10 }
  ],
  "period": {
    "days": 7,
    "start_date": "2026-05-01T04:00:00Z"
  },
  "timestamp": "2026-05-08T04:00:00Z"
}
```

---

## ⚡ 7. API OPTIMIZADA — `/api/ik/`

> Endpoints optimizados para reducir round-trips. **Auth requerida** excepto login.

### `POST /api/ik/login/`
Login optimizado (devuelve menos datos que el original).

**Body:**
```json
{
  "email": "usuario@ejemplo.com",
  "password": "tu_password"
}
```

**Ejemplo:**
```bash
curl -X POST "https://tu-dominio.com/api/ik/login/" \
  -H "Content-Type: application/json" \
  -d '{"email":"usuario@ejemplo.com","password":"tu_password"}'
```

**Respuesta:**
```json
{
  "access_token": "a1b2c3d4e5f6...",
  "user": {
    "id": 1,
    "email": "usuario@ejemplo.com",
    "username": "juanperez",
    "first_name": "Juan",
    "last_name": "Perez",
    "is_staff": false
  },
  "points_summary": {
    "total": 5,
    "owned_ids": [1, 2, 3],
    "viewed_ids": [4, 5],
    "all_ids": [1, 2, 3, 4, 5]
  }
}
```

---

### `POST /api/ik/batch/telemetry/`
Telemetría multi-punto en una sola llamada.

**Body:**
```json
{
  "point_ids": [1, 2, 3, 4, 5],
  "hours": 1
}
```
> Máximo 50 puntos por request.

**Ejemplo:**
```bash
curl -X POST "https://tu-dominio.com/api/ik/batch/telemetry/" \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"point_ids":[1,2,3],"hours":1}'
```

**Respuesta:**
```json
{
  "data": {
    "1": {
      "point_info": {
        "id": 1,
        "title": "Punto P-01",
        "project": "Proyecto Alpha",
        "client": "Cliente Beta"
      },
      "latest": {
        "id": 999,
        "date_time_medition": "2026-05-08T04:00:00Z",
        "date_time_last_logger": "2026-05-08T03:55:00Z",
        "total": 150000,
        "total_diff": 2.3,
        "total_today_diff": 45.6,
        "flow": 12.5,
        "nivel": 3.2,
        "water_table": 2.8,
        "is_error": false,
        "send_dga": true,
        "n_voucher": "ABC123"
      }
    },
    "2": {
      "point_info": { ... },
      "latest": null,
      "no_data_reason": "No records in last 1 hours"
    }
  },
  "meta": {
    "requested": 3,
    "returned": 2,
    "time_window_hours": 1,
    "timestamp": "2026-05-08T04:00:00Z"
  }
}
```

---

### `POST /api/ik/batch/stats/`
Estadísticas agregadas multi-punto.

**Body:**
```json
{
  "point_ids": [1, 2, 3],
  "days": 30
}
```

**Ejemplo:**
```bash
curl -X POST "https://tu-dominio.com/api/ik/batch/stats/" \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"point_ids":[1,2,3],"days":30}'
```

**Respuesta:**
```json
{
  "data": {
    "1": {
      "total_consumption": 850.5,
      "record_count": 720,
      "last_record": "2026-05-08T04:00:00Z",
      "period_days": 30
    }
  }
}
```

---

## 🔑 8. PASSWORD RESET — `/api/password_reset/`

Endpoints estándar de `django_rest_passwordreset`. **Sin auth**.

### `POST /api/password_reset/`
Solicitar email de reset.

**Body:**
```json
{
  "email": "usuario@ejemplo.com"
}
```

---

### `POST /api/password_reset/confirm/`
Confirmar nuevo password.

**Body:**
```json
{
  "token": "abc123...",
  "password": "nuevo_password123"
}
```

---

### `POST /api/password_reset/validate_token/`
Validar si un token es válido.

**Body:**
```json
{
  "token": "abc123..."
}
```

---

## 🤖 9. CHATBOT — `/api/chat-bot/`

Webhook para Google Chat. **Sin auth** (maneja su propia validación interna).

### `POST /api/chat-bot/`
Recibe eventos de Google Chat.

**Body:** JSON de evento Google Chat (types: `ADDED_TO_SPACE`, `MESSAGE`, `CARD_CLICKED`, `APP_COMMAND`).

> **Nota:** Este endpoint es para la integración con Google Chat, no para uso directo del frontend.

---

## 🛡️ 10. ADMIN PERSONALIZADO

> Requiere `staff_member_required` (sesión de Django Admin).

### `GET /admin/dashboard/`
Dashboard administrativo HTML con filtros y métricas.

**Query params:**
- `project` — ID de proyecto
- `point` — ID de punto
- `veracidad_periodo` — `trimestre`, `mes`, `semestre`, `año`
- `provider_filter` — `all`, `thethings`, `novus`, `tdata`
- `variable_filter` — `all`, `caudal`, `promedio`
- `error_page` — Número de página para paginación de errores

---

### `GET /admin/telemetry-monitoring/`
Vista HTML de monitoreo de telemetría.

---

### `GET /admin/telemetry-monitoring/api/`
API JSON de monitoreo en tiempo real.

---

### `GET /admin/telemetry-monitoring/api/point/{point_id}/records/`
Últimos 20 registros de un punto específico.

---

## 📋 RESUMEN RÁPIDO DE MODELOS

### InteractionDetail (Telemetría)
```json
{
  "id": 1,
  "date_time_medition": "2026-05-08T04:00:00Z",
  "date_time_last_logger": "2026-05-08T03:55:00Z",
  "flow": 12.5,
  "total": 150000,
  "total_diff": 2.3,
  "total_today_diff": 45.6,
  "nivel": 3.2,
  "water_table": 2.8,
  "pulses": 120,
  "send_dga": true,
  "return_dga": null,
  "n_voucher": "ABC123",
  "is_error": false,
  "is_partial": false,
  "days_not_conection": 0,
  "notification": null,
  "catchment_point": 42,
  "created": "2026-05-08T04:00:00Z",
  "modified": "2026-05-08T04:00:00Z"
}
```

### CatchmentPoint (Punto de Captación)
```json
{
  "id": 42,
  "title": "Punto P-01",
  "frecuency": "60",
  "lat": -33.456,
  "lon": -70.648,
  "active": true,
  "is_thethings": true,
  "is_novus": false,
  "is_tdata": false,
  "project": 5,
  "owner_user": 1,
  "users_viewers": [2, 3],
  "created": "2025-01-01T00:00:00Z",
  "modified": "2026-05-01T00:00:00Z"
}
```

### NotificationsCatchment (Notificación/Alerta)
```json
{
  "id": 1,
  "point_catchment": 42,
  "type_variable": "CAUDAL",
  "type_notification": "ALERT",
  "type_alert": "UMBRAL",
  "is_periodic": false,
  "is_active": true,
  "is_read": false,
  "is_response": false,
  "is_finish": false,
  "is_wait": false,
  "status_dga": "PENDING",
  "status_sma": "PENDING",
  "start_date": "2026-05-01",
  "end_date": null,
  "emails": ["admin@ejemplo.com"],
  "created": "2026-05-01T00:00:00Z",
  "modified": "2026-05-08T00:00:00Z"
}
```

---

## 🔧 NOTAS TÉCNICAS PARA EL FRONT

1. **Todos los endpoints CRUD** usan `Content-Type: application/json` en POST/PUT/PATCH.

2. **Paginación DRF:** La mayoría de los listados usan paginación por defecto (excepto `*_override*`). La respuesta incluye `count`, `next`, `previous`, `results`.

3. **Filtros:** Casi todos los ViewSets tienen `DjangoFilterBackend`. Puedes filtrar por cualquier campo usando `?campo=valor` o `?campo__lookup=valor`.

4. **Frecuencias de punto:** `1` = 1 min, `5` = 5 min, `10` = 10 min, `60` = 60 min. Esto afecta el límite de registros devueltos en telemetría.

5. **Archivos:** En `file_catchment`, el campo `file` es una URL al archivo subido.

6. **Errores comunes:**
   - `401 Unauthorized` → Token inválido o expirado
   - `403 Forbidden` → Usuario autenticado pero sin permisos
   - `404 Not Found` → Recurso no existe

---

*Manual generado el 2026-05-08 — SmartHydro API v1.0*
