# SmartHydro App Chat API

> **Versión:** 1.0  
> **Fecha:** 2025-05-15  
> **Base URL:** `https://api.smarthydro.app/api`  
> **Formato:** JSON  
> **Autenticación:** Token (DRF) o Session

---

## 📡 Arquitectura recomendada

Este endpoint usa el patrón **Request-Response HTTP** (POST/JSON). Para un chat contra un bot (servidor → usuario), esta es la arquitectura estándar usada por OpenAI, Anthropic, Google Gemini y la inmensa mayoría de APIs conversacionales.

| Característica | HTTP POST | SSE (Streaming) | WebSockets |
|---|---|---|---|
| **Complejidad** | Baja | Media | Alta |
| **Latencia percibida** | Espera respuesta completa | Texto en tiempo real | Texto en tiempo real |
| **Escalabilidad** | Alta (stateless) | Media | Baja (stateful) |
| **Reconexión** | Automática (HTTP) | Simple | Compleja (heartbeat) |
| **Ideal para** | Respuestas < 5s | Respuestas largas de IA | Chat P2P / multiplayer |
| **SmartHydro** | ✅ **Recomendado** | Opcional futuro | Overkill |

> **Recomendación:** Quedarse con HTTP POST. Si en el futuro la respuesta de Gemini se siente lenta (porque genera mucho texto), se puede agregar SSE como endpoint paralelo `/api/chat/stream/` sin romper nada.

---

## 🔐 Autenticación

Todas las peticiones requieren autenticación.

### Token Authentication (DRF)
```
Authorization: Token <user_api_token>
```

Obtener token vía login: `POST /api/users/login/`

---

## 🎯 Endpoint principal

### `POST /api/chat/`

Envía un mensaje del usuario al asistente inteligente y recibe la respuesta.

#### Headers
```http
Content-Type: application/json
Authorization: Token <token>
```

#### Body (Request)
```json
{
  "message": "¿Cómo está el caudal de P4?",
  "conversation_id": "session-abc-123"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `message` | `string` | ✅ | Texto de la pregunta del usuario. Máx 2000 caracteres. |
| `conversation_id` | `string` | ❌ | ID de conversación para mantener contexto entre mensajes. Si no se envía, se usa `"default"`. |

> **Nota sobre `conversation_id`:**  
> Genera un UUID por chat en tu frontend. Ejemplo: `crypto.randomUUID()` en JS.  
> Si el usuario abre 3 chats diferentes, cada uno debe tener su propio `conversation_id`.  
> Si recargas la app y quieres retomar la misma conversación, reutiliza el mismo ID.

#### Response 200 OK
```json
{
  "response": "El caudal de P4 (Iansa) es 12.5 L/s, registrado hoy a las 09:45. El nivel freático está en 8.2 m.",
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
| `response` | `string` | Texto de respuesta del asistente. Puede incluir emojis y saltos de línea (`\n`). |
| `context.client` | `string \| null` | Cliente detectado en la conversación. |
| `context.project` | `string \| null` | Proyecto detectado en la conversación. |
| `context.point` | `string \| null` | Punto de captación detectado en la conversación. |
| `conversation_id` | `string` | ID de conversación (el mismo que se envió o el default). |
| `timestamp` | `string` | Fecha UTC en formato ISO 8601. |

#### Response 400 Bad Request
```json
{
  "error": "Datos inválidos",
  "details": {
    "message": ["Este campo es requerido."]
  }
}
```

#### Response 401 Unauthorized
```json
{
  "detail": "Las credenciales de autenticación no se proveyeron."
}
```

#### Response 500 Internal Server Error
```json
{
  "error": "Ocurrió un error procesando tu mensaje.",
  "detail": "Traceback... (solo visible para staff)"
}
```

---

## 🔒 Seguridad: Alcance por Usuario

El endpoint **restringe automáticamente** todas las consultas a los puntos donde el usuario es `owner_user` o `users_viewers`. No puede ver datos de otros clientes ni puntos ajenos.

### Comportamiento por tipo de usuario

| Rol | Contexto automático | Alcance de búsqueda |
|---|---|---|
| Usuario normal | Cliente/Proyecto principal precargado | **Solo sus puntos asociados** |
| `is_staff` / `is_superuser` | Sin restricción | Todo el sistema |

> **Implementación técnica:** El motor de chatbot usa `ScopedTools`, una capa de filtrado que intercepta todas las queries de BD. Si el usuario pregunta por un cliente o punto al que no tiene acceso, el bot responde como si no existiera (sin revelar que pertenece a otro usuario).

### Ejemplo de flujo conversacional

**Request 1:**
```json
{ "message": "Dame el estado de mis puntos" }
```
**Response 1:**
```json
{
  "response": "Tienes 5 puntos activos para el cliente Iansa...",
  "context": { "client": "Iansa", "project": null, "point": null }
}
```

**Request 2 (misma conversación):**
```json
{ "message": "¿Y P4 cómo viene?", "conversation_id": "same-id" }
```
**Response 2:**
```json
{
  "response": "P4 tiene caudal 12.5 L/s y nivel 8.2 m...",
  "context": { "client": "Iansa", "project": "Proyecto Norte", "point": "P4" }
}
```

> El bot "recuerda" que estabas hablando de Iansa gracias al contexto Redis de `conversation_id`.

---

## 💬 Intenciones soportadas (sin usar IA)

El bot usa un **Intent Router** determinista que responde instantáneamente (sin llamar a Gemini) para estas consultas:

| Intención | Ejemplo de mensaje | Respuesta |
|---|---|---|
| `GLOBAL_STATUS` | `"estado general"`, `"cómo vamos"` | Resumen de salud del sistema |
| `MEASUREMENTS` | `"mediciones Iansa"`, `"datos de P4"` | Últimas lecturas |
| `HISTORY` | `"historial P4"`, `"últimos 3 días"` | Serie temporal de un punto |
| `DGA` | `"DGA Iansa"`, `"cumplimiento normativo"` | Estado de vouchers DGA |
| `ALERTS` | `"alertas"`, `"novedades"` | Notificaciones recientes |
| `CONFIG` | `"configuración de P4"` | Parámetros del punto |
| `RANKING` | `"ranking de consumo"` | Top puntos por consumo |
| `ANOMALIES` | `"anomalías"`, `"puntos pegados"` | Puntos sin variación |
| `COMPARE` | `"compara P1 con P4"` | Comparación lado a lado |
| `HELP` | `"ayuda"`, `"qué puedes hacer"` | Menú de comandos |

Si el mensaje no coincide con ninguna intención conocida, se envía a **Gemini 2.0 Flash** con el contexto del usuario.

---

## 🔄 Flujo del Frontend (React / Vue / Flutter)

```
┌─────────────┐     POST /api/chat/      ┌─────────────────┐
│   Usuario   │ ───────────────────────> │  SmartHydro API │
│  (Frontend) │   {message, conv_id}     │                 │
│             │                          │  1. Auth check  │
│             │ <─────────────────────── │  2. Infer user  │
│             │    {response, context}   │     context     │
│             │                          │  3. Intent      │
│             │                          │     routing     │
│             │                          │  4. Gemini (si  │
│             │                          │     es necesario│
└─────────────┘                          └─────────────────┘
```

### Patrón de implementación sugerido

```javascript
// Servicio de chat
async function sendMessage(message, conversationId = 'default') {
  const res = await fetch('/api/chat/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Token ${localStorage.getItem('token')}`
    },
    body: JSON.stringify({ message, conversation_id: conversationId })
  });
  return res.json(); // { response, context, conversation_id, timestamp }
}

// En tu componente de chat
const [messages, setMessages] = useState([]);
const [conversationId] = useState(() => crypto.randomUUID());

const handleSend = async (text) => {
  setMessages(prev => [...prev, { role: 'user', text }]);
  
  const data = await sendMessage(text, conversationId);
  
  setMessages(prev => [...prev, { 
    role: 'assistant', 
    text: data.response,
    context: data.context 
  }]);
};
```

---

## 🎫 Fallback a Ticket de Soporte

Si el bot no puede responder la pregunta (no encuentra datos en los puntos del usuario, o la consulta excede sus capacidades), la respuesta incluye automáticamente una **sugerencia para abrir un ticket de soporte**.

### ¿Cuándo se dispara?
- El usuario pregunta por un punto/cliente que no tiene asociado
- No hay datos recientes para responder la consulta
- La IA (Gemini) emite el tag `[TICKET]` porque no puede resolver la intención

### Ejemplo de respuesta con ticket
```json
{
  "response": "No encontré información relacionada con tu consulta en tus puntos asociados.\n\n🎫 ¿Necesitas ayuda adicional?\nNo encontré esa información en tus puntos asociados, o puede que requiera revisión manual por parte del equipo de soporte.\n\n¿Te gustaría abrir un ticket? Puedes hacerlo desde el menú de soporte de la app.",
  "context": { "client": null, "project": null, "point": null },
  "conversation_id": "session-abc-123",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

> **Nota para staff:** Los usuarios staff/admin **no** reciben la sugerencia de ticket automática, ya que tienen acceso global y el "no encontré" puede deberse a que realmente no existe el dato.

---

## ⏱️ TTL y Límites

| Recurso | Límite |
|---|---|
| Longitud máxima de `message` | 2000 caracteres |
| TTL contexto Redis (inactividad) | 15 minutos |
| Cache de respuestas frecuentes | Variable (30s - 5min) |
| Rate limit recomendado | 30 req/min por usuario |

---

## 🚀 Roadmap / Extensiones futuras (opcionales)

| Feature | Descripción | Complejidad |
|---|---|---|
| `GET /api/chat/history/` | Recuperar historial de mensajes de una conversación | Baja |
| `POST /api/chat/stream/` | SSE (Server-Sent Events) para ver la respuesta palabra por palabra | Media |
| `POST /api/chat/feedback/` | Thumbs up/down sobre una respuesta para mejorar prompts | Baja |
| Archivos adjuntos | Permitir subir imágenes/PDF para análisis | Media |

---

## 📞 Soporte

Si una respuesta es incorrecta o el bot no entiende una pregunta válida:
1. Revisa el `context` devuelto — ¿detectó el cliente/punto correcto?
2. Intenta ser más específico: `"Cliente Iansa, punto P4, caudal última hora"`
3. Los usuarios `staff` pueden ver el `detail` en errores 500.
