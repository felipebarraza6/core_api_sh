# Guía para el Frontend - Login y Carga de Datos

## Resumen

Para evitar que el login sea lento y pesado, usa la **API optimizada** (`/api/ik/login/`) en lugar del login legacy (`/api/users/login/`).

La diferencia clave:
- **Login legacy** (`/api/users/login/`): Devuelve TODOS los datos de cada punto (puede ser muy pesado)
- **Login optimizado** (`/api/ik/login/`): Devuelve solo IDs de puntos y datos del usuario (ligero)

---

## 1. Login Optimizado

```http
POST /api/ik/login/
Content-Type: application/json

{
  "email": "felipe@gmail.com",
  "password": "tu_password"
}
```

### Respuesta

```json
{
  "access_token": "abc123...",
  "user": {
    "id": 1,
    "email": "felipe@gmail.com",
    "username": "felipebarraza6",
    "first_name": "felipe",
    "last_name": "barraza",
    "is_staff": true,
    "is_superuser": true,
    "is_client_admin": false
  },
  "points_summary": {
    "total": 5,
    "owned_ids": [1, 2],
    "viewed_ids": [3, 4, 5],
    "all_ids": [1, 2, 3, 4, 5]
  }
}
```

### Qué hacer con esto en el front

1. **Guardar el token** en localStorage/cookies
2. **Guardar los datos del usuario** en tu store/context
3. **NO cargar los puntos todavía**, solo guardar los IDs
4. **Mostrar la lista de puntos** usando los IDs (puedes mostrar solo el ID o cargar los títulos después)

---

## 2. Cargar puntos bajo demanda

### Opción A: Cargar todos los puntos del usuario (sin paginación)

```http
GET /api/catchment_point/all/
Authorization: Bearer <token>
```

Devuelve los puntos con datos básicos (sin los módulos pesados).

### Opción B: Cargar un punto específico con todo el detalle

```http
GET /api/catchment_point/1/
Authorization: Bearer <token>
```

Este sí devuelve TODO: `modules.m1`, `modules.m2`, `modules.today`, `config_data`, etc.

**Recomendación:**
- En la lista/vista general: usa `/api/catchment_point/all/`
- Cuando el usuario hace clic en un punto: usa `/api/catchment_point/<id>/`

---

## 3. Estrategia recomendada para el frontend

```jsx
// 1. Login
const login = async (email, password) => {
  const res = await fetch('/api/ik/login/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  const data = await res.json();
  
  localStorage.setItem('token', data.access_token);
  setUser(data.user);
  setPointIds(data.points_summary.all_ids);
};

// 2. Cargar lista de puntos (solo básicos)
const loadPoints = async () => {
  const res = await fetch('/api/catchment_point/all/', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const points = await res.json();
  setPoints(points);
};

// 3. Cuando el usuario selecciona un punto, cargar el detalle
const loadPointDetail = async (pointId) => {
  const res = await fetch(`/api/catchment_point/${pointId}/`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const detail = await res.json();
  setSelectedPoint(detail);
};
```

---

## 4. Login legacy (solo si necesitas todo de una vez)

Si por alguna razón necesitas los datos completos de todos los puntos en el login, sigue usando:

```http
POST /api/users/login/
```

Pero ten en cuenta que puede ser **muy pesado** si el usuario tiene muchos puntos.

---

## 5. Jerarquía de permisos (para mostrar/ocultar botones)

Usa estos campos del usuario para decidir qué mostrar:

| Campo | Qué permite |
|-------|-------------|
| `is_superuser` | Todo: editar, eliminar, acceder a admin |
| `is_staff` | Acceso a dashboards y reportes administrativos |
| `is_client_admin` | Editar datos de sus clientes asignados (próximamente) |
| Ninguno | Solo lectura de sus puntos |

```jsx
const canEdit = user.is_superuser || user.is_client_admin;
const canAccessAdmin = user.is_superuser || user.is_staff;

{canEdit && <button>Editar</button>}
{canAccessAdmin && <Link to="/admin">Panel Admin</Link>}
```

---

## 6. Endpoints útiles para el dashboard

| Endpoint | Para qué sirve |
|----------|----------------|
| `GET /api/client/with-projects/` | Cargar clientes + proyectos (1 solo fetch) |
| `GET /api/catchment_point/all/?project=1` | Puntos de un proyecto |
| `GET /api/management/system_status/` | Estadísticas del sistema |
| `GET /api/management/system_map/` | Mapa completo del sistema (solo staff) |

---

## 7. Tips de performance

1. **Nunca cargues `/api/users/login/` en mobile** si el usuario tiene más de 10 puntos
2. **Usa `/api/ik/login/` siempre** y carga los datos bajo demanda
3. **Cachea los puntos** en el frontend para no repetir requests
4. **Usa `/api/catchment_point/<id>/` solo cuando el usuario hace clic** en un punto
