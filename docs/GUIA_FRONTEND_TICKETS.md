# Guía Frontend — Sistema de Tickets y SLA

> Última actualización: 2026-08-05
> Estado: listo para desarrollo frontend

## 1. Conceptos clave

### Origen (`origin`)
- `CLIENTE` → ticket real. Aplica SLA, cuenta para métricas.
- `INTERNO` → borrador/evento automático. **NO aplica SLA**. Se generan desde alertas (`ALERTA_AUTO`) o eventos del sistema (`SISTEMA`).

### Canal (`source`)
- `APP_CLIENTE`
- `APP_ADMIN`
- `ALERTA_AUTO`
- `SISTEMA`
- `CORREO`
- `TELEFONO`

### Estados de ticket
```
ABIERTO → EN_ANALISIS → EN_ORDEN_TRABAJO → ESPERA_CLIENTE → ESPERA_PROVEEDOR → RESUELTO → CERRADO
```
También existe `CANCELADO`.

### Prioridades
```
BAJA | MEDIA | ALTA | CRITICA
```

---

## 2. Endpoints

### Tickets

| Método | Endpoint | Descripción | Permisos |
|--------|----------|-------------|----------|
| GET | `/api/ik/tickets/` | Listar tickets accesibles | Autenticado |
| POST | `/api/ik/tickets/` | Crear ticket | Autenticado |
| GET | `/api/ik/tickets/<id>/` | Detalle completo | Autenticado |
| PATCH | `/api/ik/tickets/<id>/` | Editar parcial | Autenticado (staff puede más) |
| DELETE | `/api/ik/tickets/<id>/` | Eliminar lógico | Staff/superuser |
| POST | `/api/ik/tickets/<id>/assign/` | Asignar ticket | Staff |
| POST | `/api/ik/tickets/<id>/status/` | Cambiar estado | Staff |
| POST | `/api/ik/tickets/<id>/confirm-scheduled-date/` | Confirmar fecha planificada de OT | Autenticado con acceso al ticket |
| POST | `/api/ik/tickets/<id>/cancel-scheduled-date/` | Cancelar fecha planificada de OT | Autenticado con acceso al ticket |
| GET | `/api/ik/tickets/<id>/comments/` | Listar comentarios | Autenticado |
| POST | `/api/ik/tickets/<id>/comments/` | Agregar comentario (opcional `parent_id` para responder en hilo; soporta `@usuario` y `#<id_ticket>`) | Autenticado |
| DELETE | `/api/ik/tickets/<id>/comments/<cid>/` | Eliminar comentario | Staff o autor del comentario |
| GET | `/api/ik/tickets/<id>/mentionable_users/` | Usuarios etiquetables con @ (autocomplete) | Autenticado |
| GET | `/api/ik/tickets/notifications/` | Mis notificaciones in-app (`?unread_only=true`) | Autenticado |
| POST | `/api/ik/tickets/notifications/mark-read/` | Marcar leídas (`{"ids": [...]}` o `{"id": x}`) | Autenticado |
| GET | `/api/ik/tickets/<id>/attachments/` | Listar adjuntos | Autenticado |
| POST | `/api/ik/tickets/<id>/attachments/` | Subir adjunto | Autenticado |
| GET | `/api/ik/tickets/stats/` | Estadísticas | Autenticado |
| GET | `/api/ik/tickets/ranking/` | Ranking de personas (resueltos/asignados/creados) | Autenticado |
| GET | `/api/ik/tickets/my_desk/` | Mi escritorio | Autenticado |

### Categorías

| Método | Endpoint | Descripción | Permisos |
|--------|----------|-------------|----------|
| GET | `/api/ik/ticket-categories/` | Listar categorías | Autenticado |
| POST | `/api/ik/ticket-categories/` | Crear categoría | Staff |
| GET | `/api/ik/ticket-categories/<id>/` | Detalle | Autenticado |
| PATCH | `/api/ik/ticket-categories/<id>/` | Editar | Staff |
| DELETE | `/api/ik/ticket-categories/<id>/` | Desactivar | Staff |

### SLA Configs

| Método | Endpoint | Descripción | Permisos |
|--------|----------|-------------|----------|
| GET | `/api/ik/sla-configs/` | Listar configs | Admin |
| POST | `/api/ik/sla-configs/` | Crear config | Admin |
| GET | `/api/ik/sla-configs/<id>/` | Detalle | Admin |
| PATCH | `/api/ik/sla-configs/<id>/` | Editar | Admin |
| DELETE | `/api/ik/sla-configs/<id>/` | Eliminar | Admin |

> **Webhook SLA:** cada SLAConfig acepta `webhook_url`. Al vencer el SLA de un ticket con esa config, se envía un `POST` JSON (`event: "sla_overdue"`, `ticket_id`, `title`, `status`, `priority`, `client`, `point`, `assigned_to`, `overdue_items`, `notified_at`) además del correo. Si `webhook_url` está vacío, se usa `settings.SLA_OVERDUE_WEBHOOK_URL` si existe.

---

## 3. Flujo de trabajo recomendado (UI/UX)

### 3.1 Crear ticket
```http
POST /api/ik/tickets/
Content-Type: application/json
Authorization: Token <token>

{
  "points": [1],
  "title": "Título del problema",
  "description": "Descripción detallada",
  "priority": "ALTA",
  "category": 7,
  "source": "APP_ADMIN",
  "origin": "CLIENTE"
}
```

**Reglas importantes:**
- Si el usuario NO es staff, el backend fuerza `origin=CLIENTE` y `source=APP_CLIENTE`.
- Si es staff, puede elegir `origin` y `source`.
- El ticket **debe tener al menos un punto** (`points`).
- Si `origin=CLIENTE`, el backend calcula automáticamente el SLA según la config más específica.

### 3.2 Asignar ticket
```http
POST /api/ik/tickets/<id>/assign/
{
  "assigned_to": 71
}
```

### 3.3 Agregar comentario (puede cambiar estado)
```http
POST /api/ik/tickets/<id>/comments/
{
  "content": "Pasa a análisis con hardware",
  "is_internal": true,
  "status_change": "EN_ANALISIS"
}
```

**Reglas:**
- Solo staff puede crear `is_internal=true`.
- Si un staff comenta por primera vez, el backend marca `sla_responded_at` automáticamente.
- `status_change` solo lo aplica staff.
- Para pasar a `EN_ORDEN_TRABAJO` vía `status_change`, se debe enviar `work_order_category` (categoría de tipo `WORK_ORDER`); si falta o no es válida, responde `400`.

### 3.4 Cambiar estado directamente
```http
POST /api/ik/tickets/<id>/status/
{
  "status": "RESUELTO",
  "work_order_category": 25
}
```

Al pasar a `RESUELTO` o `CERRADO`, el backend registra `resolved_at` / `closed_at`.

**Reglas de `EN_ORDEN_TRABAJO`:**
- Es obligatorio enviar `work_order_category` al entrar a `EN_ORDEN_TRABAJO` (categoría de tipo `WORK_ORDER`); si falta o es de otro tipo, responde `400`.
- La categoría original del ticket (`category`) NO cambia; `work_order_category` es un campo aparte que solo aplica mientras el ticket está en `EN_ORDEN_TRABAJO`.
- Mientras esté en `EN_ORDEN_TRABAJO`, staff puede editar `work_order_category` (PATCH al ticket).
- Al salir de `EN_ORDEN_TRABAJO` (cualquier otro estado), el backend limpia `work_order_category` automáticamente.
- La respuesta del detalle incluye `work_order_category` (id) y `work_order_category_detail` (objeto completo de la categoría).

### 3.5 Confirmar fecha planificada de una OT
Cuando una OT (`category_type=WORK_ORDER`) tiene `scheduled_date` asignada, el involucrado puede confirmarla. Esto dispara un correo a quien confirma y a los involucrados del ticket (creador, asignado, operadores de categoría y dueños/visores del punto).

```http
POST /api/ik/tickets/<id>/confirm-scheduled-date/
Authorization: Token <token>
```

**Reglas:**
- Solo usuarios con acceso al ticket (staff o con acceso a sus puntos).
- Requiere `scheduled_date` asignada; si no, responde `400`.
- Si la fecha ya estaba confirmada, responde `200` sin reenviar correo (idempotente).
- Si staff cambia `scheduled_date`, la confirmación anterior se reinicia (`scheduled_date_confirmed=false`).

**Respuesta:** el detalle del ticket con los campos `scheduled_date_confirmed`, `scheduled_date_confirmed_by`, `scheduled_date_confirmed_by_name` y `scheduled_date_confirmed_at`.

**UI recomendada:** en el detalle de una OT con fecha planificada y sin confirmar, mostrar botón **"Confirmar fecha"**. Si `scheduled_date_confirmed=true`, mostrar estado confirmado con quién y cuándo.

### 3.6 Cancelar fecha planificada de una OT
Cuando una fecha confirmada (o sin confirmar) deja de servir, el involucrado puede cancelarla. Esto dispara un correo a quien cancela y a los involucrados del ticket (creador, asignado, operadores de categoría y dueños/visores del punto) y la fecha queda en espera de re-agendar.

```http
POST /api/ik/tickets/<id>/cancel-scheduled-date/
Authorization: Token <token>
Content-Type: application/json

{
  "reason": "Clima adverso impide la visita"
}
```

**Reglas:**
- Solo usuarios con acceso al ticket (staff o con acceso a sus puntos).
- Requiere `scheduled_date` asignada; si no, responde `400`.
- El motivo es opcional (`reason`).
- Si la fecha estaba confirmada, al cancelar queda `scheduled_date_confirmed=false` (se desconfirma).
- Si la fecha ya estaba cancelada, responde `200` sin reenviar correo (idempotente).
- **Re-agendar:** si staff cambia `scheduled_date` (PATCH al ticket), la cancelación anterior se reinicia (`scheduled_date_cancelled=false`, sin correo) y la nueva fecha vuelve a "esperando confirmación".

**Respuesta:** el detalle del ticket con los campos `scheduled_date_cancelled`, `scheduled_date_cancelled_by`, `scheduled_date_cancelled_by_name`, `scheduled_date_cancelled_at` y `scheduled_date_cancelled_reason`.

**UI recomendada:** estados del chip de fecha planificada:
- **Sin fecha** → nada.
- **Esperando confirmación** → botón **"Confirmar fecha"**.
- **Confirmada** → badge confirmada (quién/cuándo) + botón **"Cancelar"**.
- **Cancelada** → badge cancelada (motivo) + botón **"Re-agendar"** que abre el selector de fecha (PATCH `scheduled_date`) y vuelve a "esperando confirmación".

---

## 4. Sistema de categorías

### Tipos fijos (`category_type`)
- `SOFTWARE`
- `HARDWARE`
- `COMPLIANCE`
- `WORK_ORDER`

### Jerarquía
Cada categoría puede tener `parent`. Si tiene `parent`, es subcategoría y debe ser del mismo `category_type`.

### Operadores
Cada categoría tiene una lista de `operators` (usuarios). Cuando se crea un ticket en esa categoría, se les envía un correo de notificación.

**Configuración actual (2026-07-03):**
- Felipe → todas las categorías (testeo)
- Raymundo → todas las categorías (admin/CTO)
- Andrés → SOFTWARE
- Carlos → HARDWARE + WORK_ORDER

### Listar categorías
```http
GET /api/ik/ticket-categories/
GET /api/ik/ticket-categories/?category_type=HARDWARE
GET /api/ik/ticket-categories/?top_only=true
GET /api/ik/ticket-categories/?parent_id=2
```

---

## 5. SLA

### Configuración actual
| Prioridad | Respuesta | Resolución | Horario hábil |
|-----------|-----------|------------|---------------|
| CRITICA | 1h | 4h | L-V 9-18 |
| ALTA | 4h | 24h | L-V 9-18 |
| MEDIA | 8h | 48h | L-V 9-18 |
| BAJA | 24h | 120h | L-V 9-18 |

### Reglas de negocio
- SLA solo aplica a tickets con `origin=CLIENTE`.
- `sla_deadline_response`: límite para primera respuesta.
- `sla_deadline_resolution`: límite para resolver.
- `sla_responded_at`: se marca automáticamente cuando un staff comenta.
- El cron `notify_sla_overdue` corre cada hora y envía mail cuando se vence.

### Modo prueba actual
Por ahora las notificaciones de SLA vencido **solo llegan a** `felipebarraza@smarthydro.cl`. Mañana se habilita para todos.

---

## 6. Filtros de listado

### `/api/ik/tickets/`
- `status`: `ABIERTO`, `EN_ANALISIS`, etc.
- `origin`: `CLIENTE` | `INTERNO`
- `category`: ID de categoría
- `category_type`: `SOFTWARE`, `HARDWARE`, `COMPLIANCE`, `WORK_ORDER`
- `priority`: `BAJA`, `MEDIA`, `ALTA`, `CRITICA`
- `assigned_to`: ID de usuario
- `id`: **búsqueda parcial por ID del ticket** (`?id=4` devuelve tickets cuyo id contiene 4: 443, 45, 104…) — útil para buscadores
- `point_id`: ID de punto
- `project_id`: ID de proyecto
- `scheduled_date`: `YYYY-MM-DD`
- `has_visit_report`: `true` | `false`
- `search`: búsqueda en título/descripción
- `created_from`: `YYYY-MM-DD`
- `created_to`: `YYYY-MM-DD`

### `/api/ik/tickets/my_desk/`
Muestra tickets donde el usuario está asignado O es operador de la categoría.

Filtros: `status`, `priority`, `category`, `scheduled_date`, `search`.

---

## 7. Carga de archivos

Los archivos pueden colgar de un **ticket** (legacy), de un **comentario** o de una **tarea**. Cada archivo pertenece a un comentario **o** a una tarea.

```http
# Adjunto a nivel ticket (legacy)
POST /api/ik/tickets/<id>/attachments/

# Adjunto a un comentario (ticket + comentario)
POST /api/ik/tickets/<id>/comments/<cid>/attachments/

# Adjunto a una tarea (solo staff)
POST /api/ik/tasks/<id>/attachments/

Content-Type: multipart/form-data
Authorization: Token <token>

file: <archivo>
```

### Restricciones
- Tamaño máximo: **10 MB**
- Extensiones permitidas: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.xlsx`, `.xls`, `.doc`, `.docx`, `.txt`, `.csv`

La respuesta incluye `file_url` con URL absoluta. Si el adjunto cuelga de un comentario, el JSON incluye `comment`; si cuelga de una tarea, incluye `task`.

### Ver adjuntos por contexto
- Un **comentario** ya devuelve `attachments` dentro de cada comentario de `GET /api/ik/tickets/<id>/comments/`.
- Una **tarea** devuelve `attachments` dentro de cada tarea de `GET /api/ik/tickets/<id>/tasks/` y `GET /api/ik/tasks/<id>/`.
- El detalle del ticket (`GET /api/ik/tickets/<id>/`) incluye `tasks` con sus adjuntos y `attachments` (adjuntos a nivel ticket).

---

## 7b. Tareas por ticket

Cada ticket puede tener tareas. La tarea **registra la etapa** (`created_stage`) en que nació: es un snapshot del estado del ticket en ese momento (si el ticket cambia de estado después, la tarea conserva el original).

### Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/ik/tickets/<id>/tasks/` | listar tareas del ticket (filtros: `status`, `assigned_to`) |
| POST | `/api/ik/tickets/<id>/tasks/` | crear tarea (**solo staff**) |
| GET | `/api/ik/tasks/<id>/` | detalle de tarea |
| PATCH | `/api/ik/tasks/<id>/` | editar tarea (**solo staff**) |
| DELETE | `/api/ik/tasks/<id>/` | eliminar tarea (**solo staff**) |

### Campos

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | int | |
| `ticket` | int | id del ticket |
| `title` | string | requerido |
| `description` | text | opcional |
| `status` | string | `PENDIENTE` (default) · `EN_PROGRESO` · `COMPLETADA` · `CANCELADA` |
| `priority` | string | `BAJA` · `MEDIA` (default) · `ALTA` · `CRITICA` |
| `assigned_to` | int | id de usuario (opcional) |
| `due_date` | datetime | opcional |
| `created_stage` | string | **solo lectura** — estado del ticket al crear la tarea |
| `attachments` | array | adjuntos de la tarea |

### Ejemplo de creación
```http
POST /api/ik/tickets/443/tasks/
Authorization: Token <token>
Content-Type: application/json

{
  "title": "Revisar sensor nivel",
  "priority": "ALTA",
  "status": "PENDIENTE",
  "assigned_to": 12,
  "due_date": "2026-08-10T12:00:00Z"
}
```

**Importante:** el frontend **no** envía `created_stage`; se calcula automáticamente con el estado del ticket.

---

## 7c. Drive de archivos (`/api/ik/files/`)

Vista global tipo "drive": lista todos los archivos y a dónde pertenecen (ticket + comentario o tarea).

```http
GET /api/ik/files/
Authorization: Token <token>
```

Filtros (query params):
- `ticket_id`: id de ticket
- `project_id`: id de proyecto
- `client_id`: id de cliente
- `contexto`: `comentario` | `tarea`
- `search`: por nombre original del archivo

Respuesta paginada; cada fila incluye:
```json
{
  "id": 101,
  "ticket_id": 443,
  "ticket_title": "Falla sensor",
  "comment_id": 55,
  "comment_snippet": "Evidencia adjunta...",
  "task_id": null,
  "task_title": null,
  "project_id": 3,
  "project_name": "Proyecto Iansa",
  "client_id": 2,
  "client_name": "Iansa",
  "file_url": "https://api.smarthydro.app/media/tickets/2026/08/xxx.pdf",
  "original_name": "plano.pdf",
  "uploaded_by_name": "Felipe Barraza",
  "created": "2026-08-05T17:00:00Z"
}
```
Si cuelga de un comentario, `comment_id`/`comment_snippet` vienen poblados; si cuelga de una tarea, `task_id`/`task_title`.

---

## 8. Mi Escritorio (`/api/ik/tickets/my_desk/`)

Página principal para operadores. Debe mostrar:
1. Tickets asignados a mí.
2. Tickets en categorías donde soy operador.
3. Contadores por estado.
4. Alertas de SLA próximo a vencer / vencido.

---

## 9. Estadísticas (`/api/ik/tickets/stats/`)

Considera **solo tickets CLIENTE** (INTERNO y OPERACIONES quedan fuera).

Respuesta:
```json
{
  "total": 25,
  "by_status": {"CERRADO": 3, "EN_ANALISIS": 5, "EN_ORDEN_TRABAJO": 6, "ESPERA_CLIENTE": 1, "RESUELTO": 10},
  "by_category": {"9": 11, "12": 2, "13": 2, "14": 1, "15": 1, "18": 3, "19": 1, "21": 2, "28": 2},
  "by_category_type": {"COMPLIANCE": 2, "HARDWARE": 10, "SOFTWARE": 11, "WORK_ORDER": 2},
  "by_priority": {"ALTA": 4, "BAJA": 16, "MEDIA": 5},
  "by_origin": {"CLIENTE": 25},
  "sla_overdue_response": 0,
  "sla_overdue_resolution": 6,
  "compliance": {"total": 2, "by_status": {"RESUELTO": 2}, "sla_overdue_response": 0, "sla_overdue_resolution": 0}
}
```

Ideal para dashboard de soporte. `by_category` usa IDs → mapear con `/api/ik/ticket-categories/`.

---

## 9b. Ranking de personas (`/api/ik/tickets/ranking/`)

Cuántos tickets realizó cada persona. Solo tickets CLIENTE. Filtros: `created_at__gte`, `created_at__lte`, `project_id`, `client_id`.

```json
{
  "by_resolved": [{"user_id": 71, "name": "Andrés Nuñez", "total": 12}],
  "by_assigned": [{"user_id": 71, "name": "Andrés Nuñez", "total": 13}],
  "by_created": [{"user_id": 71, "name": "Andrés Nuñez", "total": 25}],
  "by_sla_resolution_overdue": [{"user_id": 77, "name": "Raymundo Anavalon", "total": 4}],
  "by_sla_response_overdue": [],
  "metadata": {"generated_at": "...", "filters_applied": {...}}
}
```

- `by_resolved`: resueltos (`status → RESUELTO` en activity log) + cerrados directo a `CERRADO`.
- `by_assigned`: asignación actual; los sin asignar no aparecen (`sum <= total`).
- `by_sla_resolution_overdue` / `by_sla_response_overdue`: **SLA vencidos por persona asignada** (resolución y respuesta). Mismos filtros que los KPIs del dashboard. `sum <= kpis.sla_resolution_overdue` — los vencidos sin asignar no suman aquí (aparecen en la tabla del dashboard como "sin asignar").
- Cada lista ordenada por `total` desc.

---

## 10. Notificaciones por correo

| Evento | Destinatarios |
|--------|---------------|
| Crear ticket | Operadores de la categoría |
| SLA vencido | Operadores de la categoría + usuario asignado |
| Confirmar fecha de OT | Quien confirma + creador, asignado, operadores de categoría y dueños/visores del punto |

---

## 11. Campos útiles del ticket (detalle)

```json
{
  "id": 100,
  "points": [{"id": 1, "title": "PC Descarga"}],
  "client_name": "Lecheria Valle Verde",
  "title": "...",
  "description": "...",
  "status": "EN_ANALISIS",
  "priority": "ALTA",
  "category": 7,
  "category_detail": {...},
  "source": "APP_ADMIN",
  "origin": "CLIENTE",
  "created_by": 1,
  "created_by_name": "Felipe Barraza",
  "assigned_to": 71,
  "assigned_to_name": "Andrés Nuñez",
  "sla_deadline_response": "2026-07-03T10:00:00Z",
  "sla_deadline_resolution": "2026-07-03T13:00:00Z",
  "scheduled_date": "2026-07-10",
  "scheduled_date_confirmed": true,
  "scheduled_date_confirmed_by": 5,
  "scheduled_date_confirmed_by_name": "Carlos Muñoz",
  "scheduled_date_confirmed_at": "2026-07-04T09:30:00Z",
  "scheduled_date_cancelled": false,
  "scheduled_date_cancelled_by": null,
  "scheduled_date_cancelled_by_name": null,
  "scheduled_date_cancelled_at": null,
  "scheduled_date_cancelled_reason": null,
  "visit_report": "...",
  "comments": [...],
  "activity_logs": [...],
  "attachments": [...]
}
```

---

## 12. Recomendaciones de UI

1. **Vista de tickets**: tabla con filtros laterales/superiores. Colores por prioridad y SLA.
2. **Detalle de ticket**: panel con info, timeline de comentarios/logs, acciones rápidas (asignar, cambiar estado, subir archivo).
3. **Crear ticket**: wizard con punto → tipo → categoría → prioridad → descripción.
4. **Mi Escritorio**: dashboard tipo kanban por estado.
5. **Categorías**: árbol de categorías/subcategorías. Solo staff edita.
6. **SLA**: indicador visual (verde/amarillo/rojo) según deadline.
