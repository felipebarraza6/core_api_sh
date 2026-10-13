# Notificaciones Push — Guía de integración

> **Estado del backend:** implementado y con **tests verdes (32/32)**.
> **Estado de activación:** **APAGADO**. El sistema queda inerte hasta que se
> configuren las claves VAPID y `PUSH_ENABLED=True`. Mientras tanto, ningún
> envío se produce y ningún servicio se ve afectado.

---

## 0. Cómo activarlo (producción)

Paso a paso. **Nada de esto lo hace el CD automáticamente.**

### 0.1 Generar claves VAPID (una sola vez)

```bash
pip install py-vapid
py_vapid generate-keys --applicationServerKey
```

Te entrega una clave **privada** y una **pública** (base64url).

### 0.2 Instalar la dependencia

`pywebpush` **no está en la imagen** y `scripts/deploy.sh` **no reconstruye
imágenes**, así que hay que instalarlo a mano en los dos contenedores:

```bash
docker exec django_api_secure pip install pywebpush
docker exec cron_jobs_secure    pip install pywebpush
```

> Si no se instala, **no se rompe nada**: `api/core/utils/webpush.py` hace un
> import perezoso y omite el envío con un warning en el log.

### 0.3 Variables de entorno

```bash
PUSH_ENABLED=True
VAPID_PRIVATE_KEY=<clave privada>
VAPID_PUBLIC_KEY=<clave pública>
VAPID_CLAIM_EMAIL=soporte@smarthydro.cl   # opcional
```

**Nunca** commitear las claves: van sólo en `.env` (que ya está en
`.gitignore`, aunque sepan que el historial tuvo credenciales).

### 0.4 Migración

La migración `0086` es 100% aditiva en PostgreSQL 15:

- `CREATE TABLE core_webpushsubscription` (tabla nueva)
- `ALTER TABLE core_user ADD COLUMN notify_push boolean DEFAULT true` (+3 iguales)
  → en PG 11+ esto es operación de metadatos: instantánea, sin rewrite.

```bash
docker exec django_api_secure python manage.py migrate core
```

### 0.5 Verificar

```bash
# Backend
curl -s -H "Authorization: Token <token>" https://api.smarthydro.app/api/ik/me/push/config/
# → {"enabled": true, "vapidPublicKey": "...", ...}
```

---

## 1. Qué notifica el backend

| Evento | Cuándo | Destinatarios | Categoría / flag |
|---|---|---|---|
| **Alerta de telemetría** | al crear el `AlertTrigger` (instantáneo) | `owner_user` + `users_viewers` del punto, **excluyendo staff** | `push_alerts` |
| **Respuesta en ticket** | al crear un `TicketComment` (no interno) | involucrados menos el autor y menos los mencionados | `push_tickets` |
| **Cambio de estado de ticket** | al cambiar `SupportTicket.status` | el creador del ticket | `push_tickets` |
| **Aviso general** | `NotificationsCatchment` **sin** punto de captación | todos los usuarios no-staff | `push_announcements` |

Notas importantes:

- **Severidad `INFO`** en alertas → no se envía push (consistente con Google Chat).
- **Comentarios internos** (`is_internal=True`) → no notifican al cliente.
- **Menciones `@usuario`** → siguen generando su propia notificación `MENTION`;
  el `REPLY` las excluye para no duplicar.
- El push **no toca** `AlertTrigger.notification_sent` ni `notification_error`:
  el envío a Google Chat / webhook / correo sigue siendo exclusivo de
  `alert_dispatcher.py`, que **no se modificó**.

### Latencia

El push se lanza **en el momento** de crear la alerta/ticket (no espera al
dispatcher). La latencia total sigue dominada por la ingesta de telemetría:

```
dato (cron 1 min) → alert_engine (1 min) → [push acá, instantáneo]
```

Es decir **~1–2 min**, no "instantáneo". Un tiempo real verdadero requeriría
mover la ingesta a un modelo event-driven (Redis pub/sub o webhooks entrantes),
que es otra fase.

---

## 2. Endpoints (todos nuevos, aditivos)

Base: `/api/ik/` — autenticación por `Token`.

### 2.1 Configuración
```
GET /api/ik/me/push/config/
```
```json
{
  "enabled": true,
  "vapidPublicKey": "BEl...",
  "user": {"notify_push": true, "push_tickets": true, "push_alerts": true, "push_announcements": true},
  "subscription_count": 1
}
```

### 2.2 Suscribir / desuscribir el dispositivo
```
POST   /api/ik/me/push/subscribe/
DELETE /api/ik/me/push/subscribe/
```
POST body:
```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/abc...",
  "keys": {"p256dh": "...", "auth": "..."},
  "user_agent": "Chrome 129 / Linux",
  "channel_type": "WEB"
}
```
DELETE body: `{"endpoint": "https://fcm.googleapis.com/fcm/send/abc..."}`

Validaciones: endpoint debe ser `https://`; para `channel_type=WEB` son
obligatorios `p256dh` y `auth`; máximo **10 dispositivos** por usuario (las
suscripciones inactivas se descartan primero).

### 2.3 Preferencias (desactivación individual)
```
GET  /api/ik/me/push/preferences/
POST /api/ik/me/push/preferences/
```
```json
{"notify_push": true, "push_tickets": true, "push_alerts": false, "push_announcements": true}
```
`notify_push=false` apaga **todo** el push del usuario sin borrar las
suscripciones (útil para "silenciar" y volver a activar después).

### 2.4 Prueba de envío (auto-diagnóstico)
```
POST /api/ik/me/push/test/     body opcional: {"category": "tickets"}
```
Si algo falla devuelve el motivo exacto:
`push_deshabilitado_en_backend` · `preferencia_general_desactivada` ·
`preferencia_<categoria>_desactivada` · `sin_suscripciones_activas_o_fallo_envio`.

### 2.5 Feed unificado (lo que consume la app)
```
GET /api/ik/me/notifications/?source=all|tickets|alerts|events|announcements
                              &unread_only=true
                              &limit=30&offset=0
```
```json
{
  "count": 12,
  "next": "https://.../me/notifications/?limit=30&offset=30",
  "previous": null,
  "unread_count": {"tickets": 3, "alerts": 2, "events": 0, "total": 5},
  "results": [
    {
      "id": "ticket-42",
      "source": "ticket",
      "type": "REPLY",
      "title": "Ticket #42",
      "message": "Juan respondió en el ticket #42: Bomba no enciende",
      "created": "2026-10-12T14:03:11+00:00",
      "is_read": false,
      "link": "/tickets/42"
    }
  ]
}
```

`source` values → `ticket` · `alert` · `event` · `announcement`.

`unread_count` cuenta tickets (`is_read=False`) + alertas no reconocidas de
puntos visibles. **Los avisos no cuentan** porque `is_read` de
`NotificationsCatchment` es un flag global, no por usuario.

Para **marcar como leída** se usan los endpoints existentes:
- tickets → `POST /api/ik/tickets/notifications/mark-read/` con `{"ids": [...]}`
- alertas → `PATCH /api/alert_triggers/<id>/` con `{"is_acknowledged": true}`

---

## 3. Frontend web (PWA) — copiar y pegar

### 3.1 `manifest.json` (en la raíz del sitio)

Esto es lo que habilita **"Agregar a pantalla de inicio"**, que en
**iOS 16.4+ es obligatorio** para que el push funcione.

```json
{
  "name": "SmartHydro",
  "short_name": "SmartHydro",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#1F3461",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

En `<head>`:
```html
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#1F3461">
```

### 3.2 `sw.js` (en la raíz del sitio — debe estar en el mismo origen)

```js
self.addEventListener('push', (event) => {
  let payload = { title: 'SmartHydro', body: '', url: '/' };
  try { payload = Object.assign(payload, event.data.json()); } catch (e) {}
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag: payload.tag || 'smarthydro',
      data: { url: payload.url || '/' },
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(clients.openWindow(url));
});

// El navegador cambió la suscripción: hay que re-suscribir y avisar al backend.
self.addEventListener('pushsubscriptionchange', (event) => {
  event.waitUntil(
    self.registration.pushManager.subscribe(event.oldSubscription.options)
      .then((sub) => fetch('/api/ik/me/push/subscribe/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: sub.endpoint,
          keys: { p256dh: sub.toJSON().keys.p256dh, auth: sub.toJSON().keys.auth },
          user_agent: navigator.userAgent,
        }),
      }))
  );
});
```

### 3.3 Registrar y suscribir

```js
async function activarNotificaciones() {
  const r = await fetch('/api/ik/me/push/config/', {
    headers: { Authorization: `Token ${token}` },
  }).then(r => r.json());

  if (!r.enabled) { console.log('Push no habilitado en backend'); return; }

  const permiso = await Notification.requestPermission();
  if (permiso !== 'granted') return;               // el usuario dijo que no

  await navigator.serviceWorker.register('/sw.js', { scope: '/' });

  const sub = await navigator.serviceWorker.ready.then(s => s.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(r.vapidPublicKey),
  }));

  await fetch('/api/ik/me/push/subscribe/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Token ${token}` },
    body: JSON.stringify({
      endpoint: sub.endpoint,
      keys: { p256dh: sub.toJSON().keys.p256dh, auth: sub.toJSON().keys.auth },
      user_agent: navigator.userAgent,
    }),
  });
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
}
```

### 3.4 Desactivar (obligatorio mostrarlo en la UI)

```js
// 1) Desactivar sin borrar la suscripción (se puede volver a activar)
await fetch('/api/ik/me/push/preferences/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Token ${token}` },
  body: JSON.stringify({ notify_push: false }),
});

// 2) Desactivar una categoría
await fetch('/api/ik/me/push/preferences/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Token ${token}` },
  body: JSON.stringify({ push_alerts: false }),
});

// 3) Borrar la suscripción del dispositivo (logout / "no volver a avisar")
const sub = await navigator.serviceWorker.ready.then(s => s.pushManager.getSubscription());
if (sub) {
  await fetch('/api/ik/me/push/subscribe/', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json', Authorization: `Token ${token}` },
    body: JSON.stringify({ endpoint: sub.endpoint }),
  });
  await sub.unsubscribe();
}
```

### 3.5 Badge de notificaciones sin leer

```js
setInterval(async () => {
  const r = await fetch('/api/ik/me/notifications/?unread_only=true&limit=1', {
    headers: { Authorization: `Token ${token}` },
  }).then(r => r.json());
  pintarBadge(r.unread_count.total);
}, 60000);
```

> Esto es **polling**, que coexiste bien con el push. Un tiempo real
> verdadero en la app web requeriría SSE o WebSockets (ver §5).

### 3.6 Notas por navegador

| Navegador | ¿Funciona? |
|---|---|
| Chrome / Edge / Opera (desktop y Android) | ✅ |
| Firefox | ✅ |
| Safari macOS 16.4+ | ✅ si el sitio está instalado (A2HS) |
| Safari iOS / iPadOS 16.4+ | ⚠️ **sólo** si el usuario hizo *Compartir → Agregar a pantalla de inicio* |
| Navegadores in-app (WebView de una app nativa) | ❌ |

---

## 4. App móvil nativa (React Native / Flutter)

El modelo ya está preparado: `WebPushSubscription.channel_type` acepta
`WEB` (navegador) o `FCM` (token de dispositivo nativo).

**Ruta recomendada para la app móvil:**

1. **Contenido:** consumir `GET /api/ik/me/notifications/` (el feed unificado).
   Con `unread_only=true` y un intervalo de 30–60 s se comporta como
   "tiempo real" para el usuario, sin necesidad de sockets.
2. **Push nativo:** registrar el device token de FCM y enviarlo:
   ```json
   POST /api/ik/me/push/subscribe/
   {"endpoint": "<FCM device token>", "channel_type": "FCM"}
   ```
   El backend **ya guarda** esas filas, pero el **envío FCM no está
   implementado** (requiere las credenciales del proyecto Firebase y
   `firebase-admin`). Está previsto: `send_webpush()` salta los canales que no
   sean `WEB` exactamente para poder agregar FCM sin tocar nada más.
   Alternativa sin backend nuevo: que la app use el SDK de FCM con
   "Firebase Cloud Messaging" y envíe desde Firebase directamente; el feed
   REST le sigue dando el detalle.
3. **Desactivar:** mismo endpoint `POST /api/ik/me/push/preferences/`.

---

## 5. Qué NO resuelve y cuál sería el siguiente paso

| Querían | Estado |
|---|---|
| Notificar respuesta de ticket | ✅ hecho |
| Notificar cambio de estado / aviso | ✅ hecho |
| Notificar alertas nuevas | ✅ hecho |
| Desactivar por usuario y por tipo | ✅ hecho |
| App móvil consumiendo notificaciones | ✅ feed REST listo; push FCM pendiente de credenciales |
| **Tiempo real de verdad** (segundos) | ❌ sigue en ~1–2 min por los crons de ingesta. Siguiente fase: Redis pub/sub + **SSE** (no requiere migrar a ASGI) o **Django Channels** si además se quiere chat en vivo |

---

## 6. Arquitectura y seguridad

- `api/core/models/push.py` — modelo `WebPushSubscription`
- `api/core/utils/webpush.py` — envío **fail-open**: sin claves, sin
  `pywebpush` o con excepción inesperada, devuelve `False` y loguea. **Nunca
  lanza.**
- `api/core/signals/push.py` — señales; cada receiver tiene `try/except`
  propio y el envío corre en un hilo (`threading.Thread`) para no bloquear
  requests ni el cron del motor de alertas. En tests corre síncrono
  (`settings.TESTING`) para que los asserts sean deterministas.
- `api/api_ik/views_push.py` — endpoints
- `tests/regression/test_webpush.py` — 32 tests

**Nada de esto modifica:** `alert_engine.py`, `alert_dispatcher.py`,
`signals/notifications.py`, `controllers/total.py`, `getters/tdata.py`,
ninguna respuesta JSON existente, nginx, docker-compose ni gunicorn.

### Rollback

```bash
git revert <commit>
# y en .env:
PUSH_ENABLED=False
```
La tabla `core_webpushsubscription` queda inerte; no hay que limpiar nada con
urgencia.
