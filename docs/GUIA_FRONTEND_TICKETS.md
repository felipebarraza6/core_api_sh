# Guía Frontend — Sistema de Tickets y SLA

> Última actualización: 2026-07-03
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
| GET | `/api/ik/tickets/<id>/comments/` | Listar comentarios | Autenticado |
| POST | `/api/ik/tickets/<id>/comments/` | Agregar comentario | Autenticado |
| GET | `/api/ik/tickets/<id>/attachments/` | Listar adjuntos | Autenticado |
| POST | `/api/ik/tickets/<id>/attachments/` | Subir adjunto | Autenticado |
| GET | `/api/ik/tickets/stats/` | Estadísticas | Autenticado |
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

### 3.4 Cambiar estado directamente
```http
POST /api/ik/tickets/<id>/status/
{
  "status": "RESUELTO"
}
```

Al pasar a `RESUELTO` o `CERRADO`, el backend registra `resolved_at` / `closed_at`.

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

```http
POST /api/ik/tickets/<id>/attachments/
Content-Type: multipart/form-data
Authorization: Token <token>

file: <archivo>
```

### Restricciones
- Tamaño máximo: **10 MB**
- Extensiones permitidas: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.xlsx`, `.xls`, `.doc`, `.docx`, `.txt`, `.csv`

La respuesta incluye `file_url` con URL absoluta.

---

## 8. Mi Escritorio (`/api/ik/tickets/my_desk/`)

Página principal para operadores. Debe mostrar:
1. Tickets asignados a mí.
2. Tickets en categorías donde soy operador.
3. Contadores por estado.
4. Alertas de SLA próximo a vencer / vencido.

---

## 9. Estadísticas (`/api/ik/tickets/stats/`)

Respuesta:
```json
{
  "total": 120,
  "by_status": {"ABIERTO": 80, "EN_ANALISIS": 20, ...},
  "by_category": {1: 30, 2: 50, ...},
  "by_priority": {"ALTA": 10, ...},
  "by_origin": {"CLIENTE": 10, "INTERNO": 110},
  "sla_overdue_response": 2,
  "sla_overdue_resolution": 5
}
```

Ideal para dashboard de soporte.

---

## 10. Notificaciones por correo

| Evento | Destinatarios |
|--------|---------------|
| Crear ticket | Operadores de la categoría |
| SLA vencido | Operadores de la categoría + usuario asignado |

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
