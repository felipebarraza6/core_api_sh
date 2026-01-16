# 📋 Endpoints de Gestión y Administración

## 🎯 Resumen

Se han agregado nuevos endpoints para gestionar y administrar el servicio de telemetría. Todos los endpoints requieren autenticación mediante token.

**Base URL:** `/api/management/`

---

## 📊 Endpoints Disponibles

### 1. **Estado General del Sistema**

```http
GET /api/management/system_status/
```

Obtiene el estado general del sistema de telemetría.

**Respuesta:**
```json
{
  "status": "operational",
  "statistics": {
    "total_points": 150,
    "active_telemetry": 120,
    "inactive_telemetry": 30,
    "disconnected_points": 5,
    "records_last_24h": 1440,
    "active_notifications": 12,
    "dga_queue_size": 45,
    "error_records_24h": 3
  },
  "timestamp": "2025-01-20T10:30:00-03:00"
}
```

---

### 2. **Estado de Puntos de Captación**

```http
GET /api/management/points_status/
```

Obtiene el estado detallado de los puntos de captación.

**Query Parameters:**
- `project` (opcional): Filtrar por ID de proyecto
- `client` (opcional): Filtrar por ID de cliente
- `disconnected` (opcional): `true` para solo puntos desconectados
- `active_telemetry` (opcional): `true` para solo con telemetría activa

**Ejemplo:**
```http
GET /api/management/points_status/?disconnected=true&active_telemetry=true
```

**Respuesta:**
```json
{
  "points": [
    {
      "id": 1,
      "title": "Pozo Principal",
      "project": "Proyecto A",
      "client": "Cliente X",
      "frecuency": "60",
      "provider": {
        "twin": true,
        "nettra": false,
        "novus": false
      },
      "telemetry_active": true,
      "last_interaction": {
        "date_time": "2025-01-20T10:00:00-03:00",
        "days_not_connection": 0,
        "flow": 12.5,
        "total": "12345.67",
        "nivel": 8.5,
        "is_error": false
      }
    }
  ],
  "total": 1,
  "timestamp": "2025-01-20T10:30:00-03:00"
}
```

---

### 3. **Métricas de Telemetría**

```http
GET /api/management/telemetry_metrics/
```

Obtiene métricas agregadas de telemetría.

**Query Parameters:**
- `point` (opcional): ID del punto de captación
- `days` (opcional): Días a consultar (default: 7)

**Ejemplo:**
```http
GET /api/management/telemetry_metrics/?point=1&days=30
```

**Respuesta:**
```json
{
  "metrics": {
    "total_records": 2160,
    "avg_flow": 15.3,
    "max_flow": 45.2,
    "min_flow": 2.1,
    "total_consumption": 12345,
    "avg_nivel": 8.5,
    "error_count": 5,
    "error_percentage": 0.23
  },
  "daily_records": [
    {"date": "2025-01-13", "count": 24},
    {"date": "2025-01-14", "count": 24}
  ],
  "hourly_records": [
    {"hour": "2025-01-20T09:00:00-03:00", "count": 5},
    {"hour": "2025-01-20T10:00:00-03:00", "count": 6}
  ],
  "period": {
    "start_date": "2025-01-13T10:30:00-03:00",
    "end_date": "2025-01-20T10:30:00-03:00",
    "days": 7
  },
  "timestamp": "2025-01-20T10:30:00-03:00"
}
```

---

### 4. **Activar/Desactivar Telemetría**

```http
POST /api/management/toggle_telemetry/
```

Activa o desactiva la telemetría de un punto de captación.

**Body:**
```json
{
  "point_id": 1,
  "enabled": true
}
```

**Respuesta:**
```json
{
  "message": "Telemetría activada correctamente",
  "point_id": 1,
  "telemetry_enabled": true,
  "timestamp": "2025-01-20T10:30:00-03:00"
}
```

---

### 5. **Estado de Cola DGA**

```http
GET /api/management/dga_queue_status/
```

Obtiene el estado de la cola de envío DGA.

**Respuesta:**
```json
{
  "queue_status": {
    "total": 45,
    "errors": 2,
    "old_records": 5
  },
  "by_point": [
    {
      "catchment_point__title": "Pozo Principal",
      "catchment_point__id": 1,
      "count": 20
    }
  ],
  "timestamp": "2025-01-20T10:30:00-03:00"
}
```

---

### 6. **Limpiar Cola DGA**

```http
POST /api/management/clear_dga_queue/
```

Limpia la cola de envío DGA.

**Body (opcional):**
```json
{
  "point_id": 1,
  "only_errors": true
}
```

**Respuesta:**
```json
{
  "message": "2 registros removidos de la cola DGA",
  "removed_count": 2,
  "timestamp": "2025-01-20T10:30:00-03:00"
}
```

---

### 7. **Reagregar a Cola DGA**

```http
POST /api/management/requeue_dga/
```

Reagrega registros a la cola DGA.

**Body (opcional):**
```json
{
  "point_id": 1,
  "start_date": "2025-01-01T00:00:00-03:00",
  "end_date": "2025-01-20T23:59:59-03:00",
  "only_errors": false
}
```

**Respuesta:**
```json
{
  "message": "150 registros agregados a la cola DGA",
  "added_count": 150,
  "timestamp": "2025-01-20T10:30:00-03:00"
}
```

---

### 8. **Actualizar Frecuencia de Punto**

```http
POST /api/management/update_point_frequency/
```

Actualiza la frecuencia de captación de un punto.

**Body:**
```json
{
  "point_id": 1,
  "frequency": "5"
}
```

**Valores permitidos:** `"1"`, `"5"`, `"60"` (minutos)

**Respuesta:**
```json
{
  "message": "Frecuencia actualizada a 5 minutos",
  "point_id": 1,
  "frequency": "5",
  "timestamp": "2025-01-20T10:30:00-03:00"
}
```

---

### 9. **Resumen de Notificaciones**

```http
GET /api/management/notifications_summary/
```

Obtiene un resumen de notificaciones.

**Query Parameters:**
- `days` (opcional): Días a consultar (default: 7)

**Ejemplo:**
```http
GET /api/management/notifications_summary/?days=30
```

**Respuesta:**
```json
{
  "summary": {
    "total": 50,
    "active": 12,
    "unread": 8,
    "finished": 30
  },
  "by_type": [
    {"type_notification": "ALERT", "count": 20},
    {"type_notification": "WARNING", "count": 15}
  ],
  "period": {
    "days": 7,
    "start_date": "2025-01-13T10:30:00-03:00"
  },
  "timestamp": "2025-01-20T10:30:00-03:00"
}
```

---

## 🔐 Autenticación

Todos los endpoints requieren autenticación mediante token. Incluye el token en el header:

```http
Authorization: Token <tu_token>
```

O usando Bearer:

```http
Authorization: Bearer <tu_token>
```

---

## 📝 Notas

- Todos los timestamps están en formato ISO 8601 con timezone (America/Santiago)
- Los endpoints de modificación (POST) requieren permisos de autenticación
- Los filtros de fecha aceptan formatos ISO 8601
- Los valores numéricos se devuelven como float o string según corresponda

---

## 🚀 Ejemplos de Uso

### Obtener estado general del sistema:
```bash
curl -X GET "https://api.smarthydro.app/api/management/system_status/" \
  -H "Authorization: Token tu_token_aqui"
```

### Activar telemetría de un punto:
```bash
curl -X POST "https://api.smarthydro.app/api/management/toggle_telemetry/" \
  -H "Authorization: Token tu_token_aqui" \
  -H "Content-Type: application/json" \
  -d '{"point_id": 1, "enabled": true}'
```

### Obtener métricas de los últimos 30 días:
```bash
curl -X GET "https://api.smarthydro.app/api/management/telemetry_metrics/?days=30" \
  -H "Authorization: Token tu_token_aqui"
```

---

*Documentación generada para los nuevos endpoints de gestión*

