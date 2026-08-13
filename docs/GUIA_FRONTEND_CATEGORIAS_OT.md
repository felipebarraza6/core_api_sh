# Guía Frontend — Gestión de Categorías y Órdenes de Trabajo (OT)

> Última actualización: 2026-08-04
> Base URL: `https://api.smarthydro.app/api/ik/`
> Autenticación: `Authorization: Token <token>`

---

## 1. Modelo de categorías

Toda categoría tiene un **tipo** fijo (`category_type`):

| Tipo | Descripción | ¿Dónde se usa? |
|------|-------------|----------------|
| `SOFTWARE` | Software (bugs, mejoras, soporte, integración) | `category` del ticket |
| `HARDWARE` | Hardware / infraestructura / telemetría | `category` del ticket |
| `COMPLIANCE` | Cumplimiento DGA/SMA | `category` del ticket |
| `WORK_ORDER` | Orden de Trabajo (campo + software) | **Solo** `work_order_category` |

**Regla de exclusividad:**
- `category` (categoría general del ticket) **nunca** acepta tipo `WORK_ORDER` (400 si se envía).
- `work_order_category` solo acepta **subcategorías activas de tipo `WORK_ORDER`** (el padre tipo no es válido).

### Árbol actual de categorías

```
SOFTWARE
├── N1 (1)
│   ├── Capacitaciones y reuniones técnicas (31)
│   ├── General (9)
│   └── Integración (10)
└── N2 (42)
    ├── Bug / Error (7)
    └── Mejora (8)

HARDWARE
├── Conectividad (3)       → Intermitencia, Reconexión, Sin señal
├── Infraestructura (2)    → Comunicaciones, Energía, PLC / Logger, Sensor
└── Telemetría (5)         → Datos erróneos, Reset de contador, Salto de pulsos

COMPLIANCE
└── Cumplimiento DGA (4)   → Envío de datos, Error DGA, Exceso de caudal, Retraso

WORK_ORDER  ← solo work_order_category
├── Hardware (6)
│   ├── Mantenimiento preventivo (25)
│   ├── Mantenimiento correctivo (26)
│   ├── Instalación (27)
│   └── Visita técnica (28)
└── Software (36)
    ├── Backend (40)
    ├── Backfill cumplimiento (DGA/SMA) (38)
    ├── Backfill telemetría (37)
    ├── Devops (41)
    └── Frontend (39)
```

> Los IDs mostrados son los de producción; la UI debe tratarlos como dinámicos.

---

## 2. Endpoints de categorías

### GET `/api/ik/ticket-categories/`

Lista las categorías **activas**. **Por defecto EXCLUYE las de tipo `WORK_ORDER`** — este es el endpoint para el **picker de categoría general** al crear/editar un ticket.

```http
GET /api/ik/ticket-categories/
Authorization: Token <token>
```

**Respuesta:**
```json
{
  "categories": [
    {
      "id": 1,
      "category_type": "SOFTWARE",
      "category_type_display": "Software",
      "name": "N1",
      "parent": null,
      "subcategories": [31, 9, 10],
      "operators": [],
      "operators_detail": [],
      "notify_operators_on_create": true,
      "is_active": true,
      "created": "2026-05-14T...Z",
      "modified": "2026-08-04T...Z"
    }
  ]
}
```

**Query params:**

| Parámetro | Valor | Efecto |
|-----------|-------|--------|
| `category_type` | `SOFTWARE`, `HARDWARE`, `COMPLIANCE`, `WORK_ORDER` | Filtra por tipo. Con `WORK_ORDER` se obtienen las categorías de OT (útil para el picker de OT). |
| `parent_id` | id | Solo subcategorías de ese padre. |
| `top_only` | `true` / `1` / `yes` | Solo categorías padre (`parent` nulo). |

### GET `/api/ik/ticket-categories/?category_type=WORK_ORDER`

Lista las categorías de OT (para el **selector de OT**). Ejemplo de respuesta reducida:

```json
{
  "categories": [
    { "id": 6, "category_type": "WORK_ORDER", "name": "Hardware", "parent": null, "subcategories": [25, 26, 27, 28], "is_active": true },
    { "id": 25, "category_type": "WORK_ORDER", "name": "Mantenimiento preventivo", "parent": 6, "is_active": true }
  ]
}
```

> Recomendación UI: cargar el picker de OT con este filtro solo cuando el ticket esté (o vaya a) `EN_ORDEN_TRABAJO`, y agrupar por el padre (`parent` / `subcategories`).

### Otros endpoints de categorías (staff)

| Método | Endpoint | Uso |
|--------|----------|-----|
| GET | `/api/ik/ticket-categories/<id>/` | Detalle de una categoría (incluye `subcategories`, `operators_detail`). |
| POST | `/api/ik/ticket-categories/` | Crear categoría (staff). Body: `category_type`, `name`, `parent` (opcional), `operators`, `notify_operators_on_create`, `is_active`. |
| PATCH | `/api/ik/ticket-categories/<id>/` | Editar (staff). |
| DELETE | `/api/ik/ticket-categories/<id>/` | **Desactivar** (staff) — elimina lógicamente (`is_active=false`). |

**Reglas de creación:**
- Una subcategoría debe ser del **mismo tipo** que su padre (400 si no).
- Una categoría no puede ser su propio padre.

---

## 3. Categoría de Orden de Trabajo en el ticket

El campo `work_order_category` es **apartado** de `category`:

| Campo | En el JSON del ticket | Cuándo aplica |
|-------|----------------------|---------------|
| `category` | `category`, `category_detail` | Siempre. Nunca tipo `WORK_ORDER`. |
| `work_order_category` | `work_order_category` (id), `work_order_category_detail` (objeto) | **Solo** en estado `EN_ORDEN_TRABAJO`. |

**Reglas de negocio:**
1. Al pasar un ticket a `EN_ORDEN_TRABAJO`, `work_order_category` es **obligatorio** (subcategoría activa tipo `WORK_ORDER`). Sin él → `400`.
2. Mientras el ticket está en `EN_ORDEN_TRABAJO`, staff puede **editar** `work_order_category` (PATCH al ticket).
3. Al salir de `EN_ORDEN_TRABAJO`, el backend **limpia** `work_order_category` automáticamente.
4. `category` original del ticket **no cambia** al entrar/salir de OT.

### Ejemplo: pasar un ticket a OT vía PATCH

```http
PATCH /api/ik/tickets/1234/
Authorization: Token <token>
Content-Type: application/json

{
  "status": "EN_ORDEN_TRABAJO",
  "work_order_category": 28
}
```

**Respuesta 200** (detalle):
```json
{
  "id": 1234,
  "status": "EN_ORDEN_TRABAJO",
  "category": 16,
  "category_detail": { "id": 16, "name": "Intermitencia", "category_type": "HARDWARE" },
  "work_order_category": 28,
  "work_order_category_detail": { "id": 28, "name": "Visita técnica", "category_type": "WORK_ORDER", "parent": 6 }
}
```

**Si falta `work_order_category`** → `400`:
```json
{ "error": "Debe seleccionar una categoría de orden de trabajo (work_order_category) para pasar a EN_ORDEN_TRABAJO." }
```

### Ejemplo: pasar a OT vía endpoint de estado

```http
POST /api/ik/tickets/1234/status/
Authorization: Token <token>
Content-Type: application/json

{
  "status": "EN_ORDEN_TRABAJO",
  "work_order_category": 37
}
```

### Ejemplo: pasar a OT mediante comentario con cambio de estado

```http
POST /api/ik/tickets/1234/comments/
Authorization: Token <token>
Content-Type: application/json

{
  "content": "Se genera orden de trabajo para backfill.",
  "is_internal": true,
  "status_change": "EN_ORDEN_TRABAJO",
  "work_order_category": 37
}
```

> `status_change` y `work_order_category` en comentarios solo los aplica **staff**.

### Editar la categoría de OT mientras está en OT

```http
PATCH /api/ik/tickets/1234/
Authorization: Token <token>
Content-Type: application/json

{ "work_order_category": 39 }
```

---

## 4. Flujo UI recomendado

1. **Crear/editar ticket** → selector de `category` con `GET /api/ik/ticket-categories/` (sin filtro; no trae OT).
2. **Al cambiar el estado a `EN_ORDEN_TRABAJO`** (sea vía PATCH del ticket, endpoint `/status/` o comentario con `status_change`):
   - Mostrar un selector de "Categoría de orden de trabajo" cargado con `GET /api/ik/ticket-categories/?category_type=WORK_ORDER`.
   - Agrupar visualmente por los padres **Hardware** y **Software** (campo `parent` / `subcategories`).
   - Enviar el id seleccionado como `work_order_category` junto al cambio de estado.
   - Si el usuario intenta pasar a OT sin seleccionar categoría, bloquear el envío (el backend también valida con 400).
3. **Mientras esté en OT**: mostrar `work_order_category_detail` como badge/etiqueta; permitir cambiarlo (PATCH) si hay permisos de staff.
4. **Fuera de OT**: el campo `work_order_category` viene `null` (el backend lo limpia). No mostrarlo o mostrarlo vacío.
5. **Stati/estados actuales del ticket:** `ABIERTO`, `EN_ANALISIS`, `EN_ORDEN_TRABAJO`, `ESPERA_CLIENTE`, `ESPERA_PROVEEDOR`, `RESUELTO`, `CERRADO` (+ `CANCELADO` si aplica).

---

## 5. Errores comunes (400)

| Error | Causa |
|-------|-------|
| `work_order_category` requerido al pasar a OT | Falta el campo o no es subcategoría `WORK_ORDER` activa. |
| `invalid pk "..." - object does not exist` en `category` | Se envió una categoría tipo `WORK_ORDER` (o inactiva) como `category`. |
| `La categoría de OT debe ser de tipo WORK_ORDER` | `work_order_category` apuntó a un tipo distinto. |
| `Debe ser una subcategoría de orden de trabajo` | Se envió un padre `WORK_ORDER` en vez de una subcategoría. |
