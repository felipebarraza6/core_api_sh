# Guía Frontend — SmartHydro Chat API

> **Para:** Equipo Frontend  
> **Endpoint:** `POST /api/chat/`  
> **Autenticación:** Token DRF (`Authorization: Token <token>`)

---

## 1. Contrato del Endpoint

### Request

```http
POST /api/chat/
Content-Type: application/json
Authorization: Token <user_api_token>

{
  "message": "¿Cómo está el caudal de P4?",
  "conversation_id": "session-abc-123"
}
```

| Campo | Tipo | Requerido | Máx | Descripción |
|---|---|---|---|---|
| `message` | `string` | ✅ | 2000 chars | Texto del usuario |
| `conversation_id` | `string` | ❌ | 64 chars | ID de conversación para mantener contexto. Si no se envía, se usa `"default"`. Genera un UUID por chat en tu app. |

### Response 200 OK

```json
{
  "response": "El caudal de P4 (Iansa) es 12.5 L/s...",
  "context": {
    "client": "Iansa",
    "project": "Proyecto Norte",
    "point": "P4"
  },
  "conversation_id": "session-abc-123",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `response` | `string` | Texto completo del bot. Incluye `\n` para saltos de línea. |
| `context.client` | `string \| null` | Cliente detectado en esta conversación. |
| `context.project` | `string \| null` | Proyecto detectado. |
| `context.point` | `string \| null` | Punto detectado. |
| `conversation_id` | `string` | El mismo ID que enviaste (o `"default"`). |
| `timestamp` | `string` | ISO 8601 UTC. |

### Response 401 Unauthorized

```json
{ "detail": "Las credenciales de autenticación no se proveyeron." }
```

### Response 400 Bad Request

```json
{
  "error": "Datos inválidos",
  "details": { "message": ["Este campo es requerido."] }
}
```

---

## 2. Comportamiento clave para el frontend

### Contexto automático
No es necesario que el usuario escriba el nombre del cliente en cada mensaje. El backend infiere el cliente/proyecto a partir de los puntos asociados al usuario autenticado.

### Persistencia de conversación
Manda el mismo `conversation_id` en cada mensaje del mismo chat para que el bot "recuerde" el contexto (último cliente, punto, etc.). TTL: 15 min de inactividad en Redis.

### Seguridad por usuario
El usuario **solo puede ver sus propios puntos**. Si pregunta por algo fuera de su alcance, la respuesta será:

```
No encontré información relacionada con tu consulta en tus puntos asociados.
```

### Fallback a ticket de soporte
Si el bot no puede responder, la respuesta incluye este bloque al final:

```
🎫 ¿Necesitas ayuda adicional?
No encontré esa información en tus puntos asociados, o puede que requiera
revisión manual por parte del equipo de soporte.

¿Te gustaría abrir un ticket? Puedes hacerlo desde el menú de soporte de la app.
```

**Tip para UI:** Detecta si `response` contiene `"🎫"` y muestra un botón de "Abrir ticket" prominente.

---

## 3. Intenciones que responde sin IA (instantáneo)

Estas consultas **no llaman a Gemini**, responden directo desde la base de datos:

| Mensaje ejemplo | Respuesta esperada |
|---|---|
| `"estado"`, `"cómo vamos"` | Resumen de puntos conectados/desconectados |
| `"mediciones Iansa"` | Últimas lecturas del cliente |
| `"datos de P4"` | Última medición del punto |
| `"historial P4"` | Serie temporal (últimos 7 días) |
| `"DGA Iansa"` | Estado de vouchers DGA |
| `"alertas"` | Notificaciones activas |
| `"configuración de P4"` | Parámetros técnicos del punto |
| `"ranking de consumo"` | Top puntos por consumo |
| `"anomalías"` | Puntos sin variación en 24h |
| `"ayuda"` | Menú de comandos |

---

## 4. Flujo recomendado en React

```
1. Usuario escribe mensaje → POST /api/chat/
2. Muestras "Escribiendo..." mientras esperas.
3. Recibes JSON → renderizas response (respeta \n).
4. Si context.point existe → puedes mostrar un chip/link al punto.
5. Si response incluye 🎫 → muestra CTA "Abrir ticket".
6. Guardas conversation_id en localStorage/state para retomar.
```

---

## 5. Ejemplos de request/response reales

### Ejemplo A: Estado general
**Request:** `{ "message": "estado" }`
**Response:**
```json
{
  "response": "📊 *Estado de tus puntos*\n\n✅ Conectados: 4\n🔴 Desconectados: 1\n📍 Total: 5\n\n💚 Salud: 80%",
  "context": { "client": "Iansa", "project": null, "point": null }
}
```

### Ejemplo B: Punto inexistente para este usuario
**Request:** `{ "message": "datos de PuntoAjeno" }`
**Response:**
```json
{
  "response": "No encontré información relacionada con tu consulta en tus puntos asociados.\n\n🎫 ¿Necesitas ayuda adicional?...",
  "context": { "client": null, "project": null, "point": null }
}
```

### Ejemplo C: Segundo mensaje (misma conversación)
**Request:** `{ "message": "¿Y P4?", "conversation_id": "sess-001" }`
**Response:**
```json
{
  "response": "P4 tiene caudal 12.5 L/s y nivel 8.2 m...",
  "context": { "client": "Iansa", "project": "Proyecto Norte", "point": "P4" }
}
```

---

## 6. Notas de implementación

- **Respeta los saltos de línea (`\n`)** en `response`. Úsalos para formatear tarjetas o listas.
- **No es WebSocket.** Es HTTP POST estándar. Polling no es necesario.
- **Rate limit sugerido:** máximo 1 request cada 500ms por usuario (debounce en el input).
- **El token** se obtiene del login estándar de SmartHydro (`POST /api/users/login/`).
- **conversation_id** generado con `crypto.randomUUID()` (o similar) por cada chat iniciado.
