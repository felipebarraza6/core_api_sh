# Anuncios Públicos - Guía para Frontend

> Endpoint: `GET /api/ik/announcements/public/`
> Auth: ❌ Ninguna (público)

---

## Contrato del Endpoint

### Request
```
GET /api/ik/announcements/public/?limit=10
```

| Query Param | Tipo | Default | Descripción |
|-------------|------|---------|-------------|
| `limit` | int | 20 | Máximo de anuncios a retornar (1-100) |

### Response 200
```json
{
  "count": 2,
  "announcements": [
    {
      "id": 1,
      "title": "Mantenimiento programado",
      "message": "El sistema estará en mantenimiento el sábado 10:00",
      "type": "INFO",
      "is_read": false,
      "created": "2026-05-13T10:00:00+00:00",
      "start_date": "2026-05-15",
      "end_date": "2026-05-15"
    }
  ]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | int | ID del anuncio |
| `title` | string | Título del anuncio |
| `message` | string | Mensaje completo |
| `type` | string | `INFO`, `WARNING`, `ALERT`, `CRITICAL`, `SUPPORT` |
| `is_read` | bool | `false` = no leído, `true` = leído |
| `created` | string (ISO) | Fecha de creación |
| `start_date` | string (YYYY-MM-DD) | Inicio de vigencia |
| `end_date` | string (YYYY-MM-DD) | Fin de vigencia |

---

## Código para copiar y pegar

### 1. Fetch básico (JavaScript puro)

```javascript
async function fetchAnnouncements(limit = 20) {
  try {
    const response = await fetch(`/api/ik/announcements/public/?limit=${limit}`);
    if (!response.ok) throw new Error('Error cargando anuncios');
    const data = await response.json();
    return data.announcements || [];
  } catch (error) {
    console.error('Announcements error:', error);
    return [];
  }
}

// Uso
fetchAnnouncements(10).then(announcements => {
  announcements.forEach(a => {
    console.log(a.title, a.is_read ? '✅ Leído' : '🔔 Nuevo');
  });
});
```

---

### 2. React Hook (useAnnouncements)

```javascript
import { useState, useEffect } from 'react';

export function useAnnouncements(limit = 20) {
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`/api/ik/announcements/public/?limit=${limit}`)
      .then(res => {
        if (!res.ok) throw new Error('Error cargando anuncios');
        return res.json();
      })
      .then(data => {
        setAnnouncements(data.announcements || []);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [limit]);

  return { announcements, loading, error };
}
```

---

### 3. Componente React (Banner de Anuncios)

```jsx
import React from 'react';
import { useAnnouncements } from './useAnnouncements';

export function AnnouncementBanner() {
  const { announcements, loading, error } = useAnnouncements(5);

  if (loading) return <div>Cargando anuncios...</div>;
  if (error) return null; // Silenciar errores

  // Solo mostrar los no leídos
  const unread = announcements.filter(a => !a.is_read);

  if (unread.length === 0) return null;

  return (
    <div className="announcement-banner">
      {unread.map(a => (
        <div
          key={a.id}
          className={`announcement-item announcement-${a.type.toLowerCase()}`}
        >
          <span className="announcement-title">{a.title}</span>
          <span className="announcement-message">{a.message}</span>
          <span className="announcement-badge">🔔 Nuevo</span>
        </div>
      ))}
    </div>
  );
}
```

---

### 4. Marcar como leído (requiere auth)

```javascript
async function markAsRead(announcementId, token) {
  const response = await fetch(`/api/notifications_catchment/${announcementId}/`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ is_read: true }),
  });

  if (!response.ok) throw new Error('Error marcando como leído');
  return await response.json();
}

// Uso
markAsRead(1, 'tu-token-aqui').then(() => {
  console.log('Anuncio marcado como leído');
});
```

---

### 5. CSS básico para el banner

```css
.announcement-banner {
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 8px;
}

.announcement-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(0,0,0,0.1);
}

.announcement-title {
  font-weight: bold;
  font-size: 14px;
}

.announcement-message {
  font-size: 13px;
  color: #555;
}

.announcement-badge {
  font-size: 11px;
  color: #e11d48;
}

/* Colores por tipo */
.announcement-info    { background: #dbeafe; border-left: 4px solid #2563eb; }
.announcement-warning { background: #fef3c7; border-left: 4px solid #d97706; }
.announcement-alert   { background: #fee2e2; border-left: 4px solid #dc2626; }
.announcement-critical{ background: #fecaca; border-left: 4px solid #991b1b; }
```

---

## Flujo completo sugerido

```
1. Usuario abre la app (login o home)
2. Frontend llama GET /api/ik/announcements/public/
3. Muestra solo los que tengan is_read === false
4. Usuario cierra/hace click en el anuncio
5. Frontend llama PATCH /api/notifications_catchment/{id}/ con is_read: true
6. El anuncio desaparece del banner
```
