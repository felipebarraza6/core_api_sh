# GUIA FRONTEND — Tickets v2: Menciones, Hilos, Referencias y Notificaciones

> Guía para aplicar en el frontend las nuevas funcionalidades del subsistema de
> tickets (ya desplegadas en producción). Toda la API es bajo `/api/ik/`, autenticación Token.
>
> **Fecha:** 2026-08-07

---

## 1. Resumen de cambios

| Funcionalidad | Endpoint | Método |
|---|---|---|
| Hilos de comentarios | `/api/ik/tickets/<id>/comments/` | POST con `parent_id` |
| Menciones `@usuario` | mismo endpoint (texto) + `/api/ik/tickets/<id>/mentionable_users/` (autocomplete) | POST / GET |
| Referencias `#<id_ticket>` | mismo endpoint (texto) | POST |
| Me gusta en comentarios | `/api/ik/tickets/<id>/comments/<cid>/like/` | POST (toggle) |
| Eliminar comentario | `/api/ik/tickets/<id>/comments/<cid>/` | DELETE |
| Notificaciones in-app | `/api/ik/tickets/notifications/` | GET |
| Marcar leídas | `/api/ik/tickets/notifications/mark-read/` | POST |
| Preferencia de correo | `/api/ik/me/notify-email/` | POST |

Además, el login (`POST /api/ik/login/`) ahora incluye `user.notify_email`.

---

## 2. Comentarios con hilos (reply)

### POST — crear comentario o respuesta

```
POST /api/ik/tickets/<id>/comments/
Authorization: Token <token>
Content-Type: application/json
```

**Comentario raíz:**
```json
{ "content": "Revisando la falla" }
```

**Respuesta a otro comentario (hilo):**
```json
{ "content": "Ya lo reviso", "parent_id": 123 }
```

- `parent_id` debe ser un comentario **del mismo ticket**; si no, responde `400`.
- Un cliente **no puede** responder a una nota interna (responde `404`).

**Respuesta `201`:**
```json
{
  "id": 124,
  "ticket": 42,
  "parent_id": 123,
  "author": 7,
  "author_name": "Juan Pérez",
  "content": "Ya lo reviso",
  "is_internal": false,
  "status_change": null,
  "attachments": [],
  "reply_count": 0,
  "like_count": 0,
  "liked_by_me": false,
  "created": "2026-08-07T18:00:00.000Z",
  "modified": "2026-08-07T18:00:00.000Z"
}
```

### GET — listar comentarios

```
GET /api/ik/tickets/<id>/comments/
```

Respuesta paginada. Cada ítem incluye **`parent_id`**, **`reply_count`**, y ahora
**`like_count`** y **`liked_by_me`**:

```json
{
  "count": 2,
  "results": [
    { "id": 123, "parent_id": null, "reply_count": 1, "like_count": 3, "liked_by_me": true, "content": "Revisando", "...": "..." },
    { "id": 124, "parent_id": 123, "reply_count": 0, "like_count": 0, "liked_by_me": false, "content": "Ya lo reviso", "...": "..." }
  ]
}
```

- `like_count` = total de "me gusta" del comentario.
- `liked_by_me` = si el usuario autenticado ya le dio "me gusta".

**Sugerencia de render:** lista plana (ya viene ordenada por fecha). Agrupa en el
frontend los comentarios con `parent_id != null` bajo su padre para formar el hilo,
o renderiza un indentado simple.

---

## 2b. Me gusta en comentarios (toggle)

```
POST /api/ik/tickets/<id>/comments/<cid>/like/
Authorization: Token <token>
```

- Sin body. Es un **toggle**: si ya había "me gusta" lo quita, si no lo agrega.
- Solo puede dar like quien puede ver el comentario (un cliente no puede dar like
  a notas internas → `404`).

**Respuesta `200`:**
```json
{ "ok": true, "liked": true, "like_count": 3 }
```

**Recomendación UX:** usa `liked_by_me` del listado para pintar el botón activo, y
actualiza el contador con `like_count` de esta respuesta tras el toggle.

---

## 3. Menciones `@usuario`

Al escribir un comentario, si el texto contiene `@<username>` de un usuario
**involucrado en el ticket** (creador, asignado, operadores de categoría,
owners/viewers de los puntos), ese usuario recibe:
- Email "Te mencionaron en Ticket #X: …"
- Notificación in-app (type `MENTION`)

### Autocomplete

```
GET /api/ik/tickets/<id>/mentionable_users/
Authorization: Token <token>
```

**Respuesta `200`:**
```json
{
  "users": [
    { "id": 7,  "username": "juan",    "full_name": "Juan Pérez",  "email": "juan@smarthydro.cl" },
    { "id": 12, "username": "maria.g", "full_name": "María González", "email": "maria.g@smarthydro.cl" }
  ]
}
```

- Úsalo para mostrar sugerencias al escribir `@`. El match del backend acepta
  `@username`, `@nombre`, `@apellido`, `@nombre.apellido` y `@email`.
- **Recomendación UX:** insertar siempre `@username` (el token exacto) para que el
  backend lo resuelva sin ambigüedad.
- Se ignora al propio autor y a usuarios fuera del ticket (sin error, solo no notifica).

---

## 4. Referencias cruzadas `#<id_ticket>`

Si el texto del comentario contiene `#<id>` de **otro** ticket, los involucrados de
ese ticket reciben:
- Email "Referenciaron tu ticket en #<id>: <título>"
- Notificación in-app (type `REFERENCE`, `ticket` = el ticket referenciado)

**Recomendación UX:** detecta el patrón `#\d+` en el texto y renderízalo como link a
la vista del ticket referenciado (la notificación in-app ya trae `ticket` + `ticket_title`).

---

## 5. Eliminar comentario

```
DELETE /api/ik/tickets/<id>/comments/<cid>/
Authorization: Token <token>
```

- `204` → eliminado. Se eliminan también sus adjuntos en cascada.
- Permisos: **staff/superuser** o **el autor** del comentario. Un cliente nunca
  elimina notas internas.
- `403` → sin permiso. `404` → no existe.
- Al eliminar, las respuestas (hijos) se conservan como comentarios sueltos
  (su `parent_id` queda `null`).

---

## 6. Notificaciones in-app

### GET — listar mis notificaciones

```
GET /api/ik/tickets/notifications/?unread_only=true
Authorization: Token <token>
```

Parámetros:
- `unread_only=true` → solo no leídas.
- Paginación por defecto (`count`, `next`, `previous`, `results`).

**Respuesta `200`:**
```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "unread_count": 2,
  "results": [
    {
      "id": 55,
      "notification_type": "MENTION",
      "notification_type_display": "Mención en comentario",
      "ticket": 42,
      "ticket_title": "Falla en pozo 3",
      "comment_id": 124,
      "message": "Juan Pérez te mencionó en el ticket #42",
      "is_read": false,
      "created": "2026-08-07T18:00:00.000Z"
    },
    {
      "id": 56,
      "notification_type": "REFERENCE",
      "notification_type_display": "Referencia a otro ticket",
      "ticket": 43,
      "ticket_title": "Alerta conectividad",
      "comment_id": 130,
      "message": "María González referenció tu ticket #43 desde el ticket #42",
      "is_read": false,
      "created": "2026-08-07T18:05:00.000Z"
    }
  ]
}
```

- Tipos: `MENTION`, `REFERENCE`.
- `ticket` + `ticket_title` sirven para el link directo al ticket.
- `comment_id` sirve para anclar al comentario concreto (scroll).

### POST — marcar como leídas

```
POST /api/ik/tickets/notifications/mark-read/
Authorization: Token <token>
Content-Type: application/json
```

Body (una u otra):
```json
{ "id": 55 }
```
```json
{ "ids": [55, 56] }
```

**Respuesta `200`:**
```json
{ "ok": true, "unread_count": 0 }
```

- Recomendado: el badge del menú usa `unread_count` de la respuesta del GET.
- Al hacer clic en una notificación → `mark-read` con su `id` + navegar al ticket.

---

## 7. Preferencia de correos (`notify_email`)

### Login

`POST /api/ik/login/` ahora retorna dentro de `user`:
```json
"user": { "id": 7, "email": "...", "username": "juan", "...": "...", "notify_email": true }
```

### Toggle

```
POST /api/ik/me/notify-email/
Authorization: Token <token>
Content-Type: application/json
```

```json
{ "notify_email": false }
```

**Respuesta `200`:**
```json
{ "ok": true, "notify_email": false }
```

- `false` → el usuario **no recibe correos** de tickets (menciones, referencias,
  SLA, operadores, fechas confirmadas/canceladas, asignación y cambios de estado).
  Las notificaciones **in-app siguen llegando igual**.
- Ideal para un switch en "Mi perfil" / configuración de notificaciones.

### Correos de asignación y cambio de estado

Al **asignar/reasignar** un ticket (`POST /api/ik/tickets/<id>/assign/` o
`PATCH /api/ik/tickets/<id>/` con `assigned_to`), se envía correo a:
- el **nuevo asignado**,
- los **operadores de la categoría**,
- el **creador** del ticket.

Al **cambiar el estado** (`POST /api/ik/tickets/<id>/status/`, `PATCH` con
`status`, o `status_change` en un comentario), se envía correo a los
**involucrados** del ticket (creador, asignado, operadores de la categoría y
dueños/visores de los puntos vinculados).

En ambos casos:
- Se **excluye a quien realiza la acción** (el actor no recibe su propio correo).
- Respetan la preferencia `notify_email` de cada usuario.
- El tema (`subject`) es "Te asignaron el ticket #N: ..." / "Ticket #N cambió a
  <ESTADO>: ...".

---

## 8. Checklist de integración frontend

1. [ ] Al listar comentarios, guarda `parent_id` y `reply_count`; renderiza hilos.
2. [ ] Al escribir comentarios: autocomplete de usuarios vía
       `/tickets/<id>/mentionable_users/` al detectar `@`.
3. [ ] Al escribir comentarios: detecta `#\d+` y renderízalo como link.
4. [ ] Agrega botón "Me gusta" en cada comentario: usa `liked_by_me` + `like_count`,
       hace POST toggle a `/comments/<cid>/like/` y actualiza con la respuesta.
5. [ ] En la respuesta POST del comentario, si el usuario fue mencionado, muestra
       confirmación visual (opcional).
6. [ ] Agrega botón "Eliminar" en comentarios propios y en staff; llama al DELETE
       y refresca la lista.
7. [ ] Menú/badge de notificaciones: GET `/tickets/notifications/?unread_only=true`
       para el contador; marcar leídas al abrir.
8. [ ] En perfil: switch de `notify_email` (lee el valor del login, escribe vía
       `/me/notify-email/`).

---

## 9. Notas para administradores (no-frontend)

- **Webhook SLA:** campo `webhook_url` en SLAConfig (admin o API
  `/api/ik/sla-configs/`). Al vencer el SLA se envía un `POST` JSON
  (`event: "sla_overdue"`) a esa URL además del correo. Si queda vacío, se usa
  `settings.SLA_OVERDUE_WEBHOOK_URL` (variable de entorno) si existe.
- **Preferencia por usuario:** también editable desde el admin de Django (campo
  `notify_email` en Usuarios).
