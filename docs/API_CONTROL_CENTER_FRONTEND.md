# Centro de Control — Guía para Frontend

> **Endpoints nuevos para el Centro de Control React**  
> **Base URL:** `https://api.smarthydro.app/api/ik/control_center/`  
> **Auth:** Token (`Authorization: Token <token>`)  
> **Throttle:** 60 req/minuto por usuario

---

## Índice

1. [GET general_stats/](#1-get-general_stats)
2. [GET daily_summary/](#2-get-daily_summary)

---

## 1. GET `/api/ik/control_center/general_stats/`

### Request

```
GET /api/ik/control_center/general_stats/
Authorization: Token <token>
```

Sin query params. Retorna KPIs globales del usuario autenticado.

### Response

```json
{
  "points": {
    "total": 193,
    "with_telemetry": 180,
    "warnings": 27,
    "with_compliance": 45
  },
  "status_today": {
    "connected": 131,
    "disconnected": 49
  },
  "projects": [
    { "id": 2, "name": "Iansa Chillán - Iansa" },
    { "id": 34, "name": "Iansa Quepe - Iansa" }
  ],
  "chat_quota": {
    "limit": 12,
    "used": 3,
    "remaining": 9
  }
}
```

### Campos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `points.total` | int | Total de puntos visibles para el usuario |
| `points.with_telemetry` | int | Puntos con perfil de telemetría configurado |
| `points.warnings` | int | Total de eventos del sistema (SystemEvent) en los puntos del usuario |
| `points.with_compliance` | int | Puntos con compliance DGA/SMA configurado |
| `status_today.connected` | int | Puntos con al menos 1 registro de telemetría hoy |
| `status_today.disconnected` | int | `with_telemetry - connected` (nunca negativo) |
| `projects[]` | array | Lista de proyectos del usuario. Admin ve `"Proyecto - Cliente"`, usuario normal ve solo `"Proyecto"` |
| `chat_quota` | object | Límite diario de preguntas al chat interpretativo |

### Reglas por rol

| Rol | `projects[].name` | Puntos visibles |
|-----|-------------------|-----------------|
| **Staff/Superuser** | `"Iansa Chillán - Iansa"` (incluye cliente) | Todos los del sistema |
| **Usuario normal** | `"Iansa Chillán"` (solo nombre) | `owner_user` + `users_viewers` |

---

## 2. GET `/api/ik/control_center/daily_summary/`

### Request

```
GET /api/ik/control_center/daily_summary/?start_date=2026-06-01&end_date=2026-06-24&project_id=2&point_id=152
Authorization: Token <token>
```

### Query Params

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `start_date` | string (YYYY-MM-DD) | Hoy - 6 días | Inicio del rango |
| `end_date` | string (YYYY-MM-DD) | Hoy | Fin del rango |
| `project_id` | int | — | Filtrar consumo por proyecto (no afecta dropdowns de proyectos) |
| `point_id` | int | — | Filtrar consumo a un punto específico |

**Límites:** Máximo 92 días entre start y end.

### Response

```json
{
  "date_range": ["2026-06-01", "2026-06-02", ..., "2026-06-24"],
  "days": {
    "2026-06-01": { "total_consumption": 47775.0 },
    "2026-06-02": { "total_consumption": 45669.0 },
    "2026-06-03": { "total_consumption": 47351.0 }
  },
  "projects": [
    { "id": 2, "name": "Iansa Chillán - Iansa" },
    { "id": 34, "name": "Iansa Quepe - Iansa" }
  ],
  "points": [
    { "id": 152, "title": "P2", "project_id": 2 },
    { "id": 110, "title": "P3", "project_id": 2 }
  ]
}
```

### Campos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `date_range[]` | array[string] | Todos los días del rango solicitado |
| `days.<fecha>.total_consumption` | float | Suma de `total_diff` del día para los puntos filtrados (m³) |
| `projects[]` | array | **Siempre completo** — todos los proyectos del usuario (para dropdown) |
| `points[]` | array | **Filtrado por `project_id`** si ese filtro está activo, sino completo |

### Comportamiento de filtros

| Filtro aplicado | `projects` | `points` | `days` |
|----------------|------------|----------|--------|
| Ninguno | 69 proyectos | 193 puntos | Consumo total del usuario por día |
| `?project_id=2` | 69 proyectos | **5 puntos** (solo Iansa Chillán) | Consumo del proyecto por día |
| `?project_id=2&point_id=152` | 69 proyectos | **5 puntos** | Consumo de P2 por día |
| `?point_id=152` | 69 proyectos | 193 puntos | Consumo de P2 por día |

### Reglas por rol (misma lógica que general_stats)

- **Staff/Superuser:** `projects[].name` incluye cliente, ve todos los puntos
- **Usuario normal:** `projects[].name` solo el nombre del proyecto, ve solo sus puntos asignados
- **Usuario sin puntos:** `projects=[]`, `points=[]`, todos los días en 0

### Ejemplo: Iansa Chillán, junio 2026

```
GET /api/ik/control_center/daily_summary/?start_date=2026-06-01&end_date=2026-06-24&project_id=2
```

```json
{
  "days": {
    "2026-06-01": { "total_consumption": 6794.0 },
    "2026-06-02": { "total_consumption": 6319.0 },
    ...
    "2026-06-24": { "total_consumption": 8633.0 }
  },
  "projects": [ ... /* todos */ ],
  "points": [
    { "id": 152, "title": "P2", "project_id": 2 },
    { "id": 110, "title": "P3", "project_id": 2 },
    { "id": 2,   "title": "P4", "project_id": 2 },
    { "id": 109, "title": "P5", "project_id": 2 },
    { "id": 111, "title": "P6", "project_id": 2 }
  ]
}
```

### Errores

| Código | Causa |
|--------|-------|
| 400 | Fecha inválida (no YYYY-MM-DD) |
| 400 | `start_date` posterior a `end_date` |
| 400 | Rango > 92 días |
| 400 | `project_id` o `point_id` no es entero |
| 401 | Token ausente o inválido |

---

---

## 3. GET `/api/ik/control_center/project_points/`

Select dropdown de puntos por proyecto. Muestra `nombre (código_obra)` cuando el punto tiene código DGA.

### Request

```
GET /api/ik/control_center/project_points/?project_id=2
Authorization: Token <token>
```

### Query Params

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `project_id` | int | ✅ Sí | ID del proyecto para filtrar puntos |

### Response

```json
{
  "points": [
    { "id": 152, "name": "P2 (OB-1603-24)" },
    { "id": 110, "name": "P3 (OB-1603-25)" },
    { "id": 2,   "name": "P4 (OB-1602-22)" },
    { "id": 109, "name": "P5 (OB-1603-393)" },
    { "id": 111, "name": "P6 (OB-1603-392)" }
  ]
}
```

El `name` incluye el código de obra DGA entre paréntesis si el punto lo tiene configurado. Si no tiene código, solo el título.

### Reglas por rol

- **Staff/Superuser:** Ve todos los puntos del proyecto
- **Usuario normal:** Ve solo los puntos donde es `owner_user` o `users_viewers`
- **Proyecto inexistente o sin puntos:** Retorna `{"points": []}`

### Errores

| Código | Causa |
|--------|-------|
| 400 | `project_id` no enviado o no es entero |
| 401 | Token ausente o inválido |

---

---

## 4. GET `/api/ik/control_center/list/`

Lista paginada de puntos de captación con datos agregados de consumo, caudal,
nivel y warnings para un **día específico**. Cada fila representa un punto.

### Request

```
GET /api/ik/control_center/list/?date=2026-06-24&project_id=2&page=1&page_size=10
Authorization: Token <token>
```

### Query Params

| Parámetro | Tipo | Requerido | Default | Descripción |
|-----------|------|-----------|---------|-------------|
| `date` | YYYY-MM-DD | ✅ Sí | — | Día a consultar |
| `project_id` | int | ❌ | — | Filtrar por proyecto |
| `order_by` | string | ❌ | — | `consumption` \| `-consumption` \| `avg_flow` \| `-avg_flow` \| `avg_level` \| `-avg_level` |
| `page` | int | ❌ | 1 | Número de página |
| `page_size` | int | ❌ | 10 | Items por página (máximo 50) |

### Response

```json
{
  "count": 193,
  "next": "?date=2026-06-24&page=2",
  "previous": null,
  "results": [
    {
      "point_id": 183,
      "point_name": "Agua Potable",
      "project_id": 62,
      "project_name": "Promasa - Promasa",
      "is_telemetry": true,
      "is_form": false,
      "status": "connected",
      "measurements_count": 17,
      "consumption": 14.0,
      "avg_flow": 0.21,
      "avg_level": 2.66,
      "water_table": 5.54,
      "variables": ["CAUDAL_PROMEDIO", "NIVEL", "TOTALIZADO"],
      "warnings_count": 0
    }
  ]
}
```

### Campos por punto

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `point_id` | int | ID del punto |
| `point_name` | string | Nombre (title) del punto |
| `project_id` | int \| null | ID del proyecto |
| `project_name` | string \| null | Nombre del proyecto (admin: `"Proyecto - Cliente"`) |
| `is_telemetry` | bool | Tiene telemetría configurada |
| `is_form` | bool | Es punto de ingreso por formulario |
| `status` | string | `"connected"` si tuvo datos ese día, si no `"disconnected"` |
| `measurements_count` | int | Cantidad de registros de telemetría ese día |
| `consumption` | float | Consumo total del día en m³ |
| `avg_flow` | float \| null | Caudal promedio del día en L/s (solo si el punto tiene variables tipo CAUDAL) |
| `avg_level` | float \| null | Nivel promedio del día en m (solo si el punto tiene variables NIVEL o NIVEL_FREATICO) |
| `water_table` | float \| null | Nivel freático promedio del día en m |
| `variables` | string[] | Lista de type_variable disponibles en el punto |
| `warnings_count` | int | Cantidad de SystemEvent del punto para ese día |

### Variables para columnas (frontend)

El frontend puede activar columnas según los valores del array `variables` de cada punto:

- Si incluye `"TOTALIZADO"` → muestra columna **Consumo (m³)**
- Si algún valor contiene `"CAUDAL"` → muestra columna **Caudal prom. (L/s)**
- Si incluye `"NIVEL"` o `"NIVEL_FREATICO"` → muestra columna **Nivel prom. (m)**

### Ordenamiento

`order_by` sigue la convención DRF:
- `consumption` / `avg_flow` / `avg_level` → **descendente** (mayor → menor)
- `-consumption` / `-avg_flow` / `-avg_level` → **ascendente** (menor → mayor)
- Si no se envía o el valor es inválido → ordena por `point_name` ascendente

### Reglas por rol

- **Staff/Superuser:** `project_name` incluye `" - {cliente}"`. Ve todos los puntos.
- **Usuario normal:** `project_name` solo el nombre. Ve solo sus puntos (owner + viewer).
- **Usuario sin puntos:** `count: 0, results: []`

### Errores

| Código | Causa |
|--------|-------|
| 400 | `date` no enviado |
| 400 | `date` con formato inválido (no YYYY-MM-DD) |
| 400 | `project_id` no es entero |
| 401 | Token ausente o inválido |

---

## 5. Flujo de navegación sugerido

1. **Al cargar:** `general_stats/` para KPIs + `daily_summary/` (default 7 días) para el calendario
2. **Select proyecto:** `project_points/?project_id=X` para poblar el dropdown de puntos
3. **Tabla de puntos:** `list/?date=YYYY-MM-DD&project_id=X&page=1` para la tabla paginada del día
4. **Ordenar:** `list/?date=...&order_by=consumption` para ordenar por consumo descendente
5. **Select punto:** `daily_summary/?project_id=X&point_id=Y` para consumo del punto
6. **Cambiar rango:** `daily_summary/?start_date=...&end_date=...` con filtros activos
