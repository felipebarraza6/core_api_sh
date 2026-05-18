# Guía de Reportes para el Frontend

## Resumen

Ahora todos los reportes del admin se pueden generar directamente desde el frontend llamando a endpoints API. Devuelven archivos Excel listos para descargar.

---

## 1. Reporte de Puntos Activos (ya existía)

```http
GET /reports/active-points/
Authorization: Bearer <token>
```

Devuelve Excel con todos los puntos activos (telemetría encendida), ordenados por cliente/proyecto.

---

## 2. Reporte por Proyecto

```http
GET /api/reports/by-project/?project_id=1
Authorization: Bearer <token>
```

Genera un Excel completo con:
- Hoja "Resumen Completo": indicadores de todos los puntos del proyecto
- Una hoja por cada punto con detalle de últimas mediciones

**Query params:**
| Param | Requerido | Descripción |
|-------|-----------|-------------|
| `project_id` | Sí | ID del proyecto |

---

## 3. Reporte por Punto

```http
GET /api/reports/by-point/?point_id=1&year=2025&month=5
Authorization: Bearer <token>
```

Genera Excel detallado de un punto específico:
- Hoja "Resumen Anual" con indicadores y últimos envíos DGA
- Una hoja por cada mes con gráficos

**Query params:**
| Param | Requerido | Descripción |
|-------|-----------|-------------|
| `point_id` | Sí | ID del punto |
| `year` | No | Año (default: año actual) |
| `month` | No | Mes 1-12 (default: todo el año) |

---

## 4. Reporte Último Mes Completo

```http
GET /api/reports/last-month/?project_id=1
Authorization: Bearer <token>
```

Genera Excel del **mes anterior completo** (por ejemplo, si estamos en mayo, genera abril).

**Query params:**
| Param | Requerido | Descripción |
|-------|-----------|-------------|
| `project_id` | No | Filtrar por proyecto |
| `point_ids` | No | Lista de IDs separados por coma (ej: `1,2,3`) |

---

## 5. Reporte Último Año Completo

```http
GET /api/reports/last-year/?project_id=1
Authorization: Bearer <token>
```

Genera Excel del **año anterior completo**.

**Query params:**
| Param | Requerido | Descripción |
|-------|-----------|-------------|
| `project_id` | No | Filtrar por proyecto |
| `point_ids` | No | Lista de IDs separados por coma |

---

## 6. Reporte Anual Comprimido (Resumen)

```http
GET /api/reports/annual-compressed/?project_id=1
Authorization: Bearer <token>
```

Genera Excel anual comprimido, solo con resúmenes (más liviano).

**Query params:**
| Param | Requerido | Descripción |
|-------|-----------|-------------|
| `project_id` | No | Filtrar por proyecto |
| `point_ids` | No | Lista de IDs separados por coma |

---

## Cómo descargar desde el frontend

```jsx
const downloadReport = async (url, filename) => {
  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok) {
    const error = await response.json();
    alert(error.error || 'Error generando reporte');
    return;
  }

  // Crear blob y descargar
  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(downloadUrl);
};

// Ejemplo: descargar reporte del proyecto 1
const handleDownloadProject = () => {
  downloadReport(
    '/api/reports/by-project/?project_id=1',
    'reporte_proyecto.xlsx'
  );
};

// Ejemplo: descargar reporte del punto 5, mes de mayo 2025
const handleDownloadPoint = () => {
  downloadReport(
    '/api/reports/by-point/?point_id=5&year=2025&month=5',
    'reporte_punto_mayo.xlsx'
  );
};
```

---

## Reportes del Admin Dashboard (solo staff)

El dashboard de admin (`/admin/dashboard/`) tiene métricas avanzadas que también se pueden consultar por API:

```http
GET /api/management/system_status/
GET /api/management/points_status/?project=1
GET /api/management/telemetry_metrics/?point=1&days=7
GET /api/management/dga_queue_status/
GET /api/management/notifications_summary/
```

Todas requieren `Authorization: Bearer <token>` y usuario autenticado.
