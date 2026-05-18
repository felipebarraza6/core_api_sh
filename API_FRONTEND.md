# 📡 API FRONTEND — Centro de Control SmartHydro

> **Base URL:** `https://api.smarthydro.app`  
> **Auth:** `Authorization: Token <token>` en todos los endpoints excepto login

---

## 🔐 1. LOGIN

```http
POST /api/ik/login/
Content-Type: application/json
```

**Body:**
```json
{
  "email": "usuario@smarthydro.cl",
  "password": "..."
}
```

**Respuesta:**
```json
{
  "access_token": "a49a1bfd3741c40ec3b72d56a2ed8e9fc2c83e30",  // Token para Authorization header
  "user": {
    "id": 1,                  // ID del usuario
    "email": "...",           // Email
    "username": "...",        // Username
    "first_name": "...",      // Nombre
    "last_name": "...",       // Apellido
    "is_staff": false,        // true = admin/staff
    "is_superuser": false,    // true = superadmin
    "is_client_admin": false  // true = puede editar datos de sus clientes
  },
  "points_summary": {
    "total": 5,               // Total de puntos visibles
    "owned_ids": [1, 2],      // IDs de puntos que le pertenecen
    "viewed_ids": [3, 4, 5],  // IDs de puntos compartidos (viewer)
    "all_ids": [1, 2, 3, 4, 5] // Todos los IDs combinados
  }
}
```

---

## 📍 2. SELECT DE PUNTOS (Dropdown)

```http
GET /api/ik/my_points/
Authorization: Token <token>
```

**Para qué sirve:** Poblar el select/dropdown de puntos del Centro de Control.  
**Orden:** Alfabético por nombre (`title`).

**Respuesta:**
```json
[
  {
    "id": 1,                          // ID del punto (value del option)
    "title": "PC Descarga",           // Nombre del punto (texto del option)
    "project_name": "SMA",            // Nombre del proyecto (optgroup o subtítulo)
    "client_name": "Lecheria Valle Verde",  // Cliente (badge)
    "frecuency": "1",                 // Frecuencia: 1, 5, 10, 60 (minutos)
    "is_telemetry": true,             // true = tiene telemetría activa (punto verde)
    "is_dga_compliance": true,        // true = envía datos a DGA (badge DGA)
    "code_dga": "7511",               // Código de obra DGA (tooltip o columna)
    "is_owner": true,                 // true = le pertenece (icono propio)
    "is_viewer": false                // true = compartido (icono compartido)
  }
]
```

**Reglas de permisos:**
- Usuario normal: solo sus puntos (owner + viewer)
- Staff/Superuser: todos los puntos (191)

---

## 📊 3. KPIs DEL DASHBOARD (Stats Generales)

```http
GET /api/ik/dashboard_stats/
Authorization: Token <token>
```

**Para qué sirve:** Mostrar las tarjetas/resumen general del Centro de Control.  
**Filtro:** Stats del usuario autenticado (sus puntos). Admin ve stats globales.

**Respuesta:**
```json
{
  "meta": {
    "date": "2026-05-09",                       // Fecha actual (YYYY-MM-DD)
    "date_formatted": "Sábado 9 de mayo, 2026", // Fecha legible en español
    "generated_at": "2026-05-09T06:49:40Z",     // Timestamp de generación
    "timezone": "America/Santiago"              // Zona horaria
  },
  "points": {
    "total": 191,              // Total de puntos visibles
    "with_telemetry": 154,     // Puntos con telemetría activa
    "without_telemetry": 37,   // Puntos sin telemetría
    "with_gps": 17,            // Puntos con lat/lon configurados
    "with_dga_compliance": 107 // Puntos enviando a DGA (con código)
  },
  "telemetry_today": {
    "connected": 148,          // Puntos que enviaron datos hoy
    "disconnected": 6,         // Puntos con telemetría pero sin datos hoy
    "without_telemetry": 37    // Puntos que nunca tuvieron telemetría
  },
  "notifications": {
    "total_active": 364,       // Alertas/notificaciones activas
    "unread": 40,              // Notificaciones sin leer
    "by_type": {               // Desglose por tipo de alerta
      "WARNING": 354,
      "SUPPORT": 7,
      "ALERT": 3
    },
    "by_variable": {           // Desglose por variable que disparó la alerta
      "TOTALIZADO": 355,
      "CAUDAL": 4,
      "TODOS": 4,
      "NIVEL": 1
    }
  },
  "dga_summary": {
    "by_type": {               // Tipos de captación DGA
      "SUBTERRANEO": 182,
      "SUPERFICIAL": 9
    },
    "by_standard": {           // Estándar normativo DGA
      "MAYOR": 74,
      "SIN_ESTANDAR": 67,
      "MEDIO": 28,
      "MENOR": 7,
      "CAUDALES_MUY_PEQUENOS": 15
    }
  }
}
```

---

## 📡 4. RESUMEN DE PUNTOS CON TELEMETRÍA

```http
GET /api/ik/points_summary/
Authorization: Token <token>
```

**Para qué sirve:** Listado completo de puntos con última telemetría incluida. Ideal para el mapa y la tabla principal del Centro de Control.  
**Performance:** Una sola query, optimizado con subqueries.

**Respuesta:**
```json
{
  "points": [
    {
      "id": 77,                         // ID del punto
      "title": "P 2",                   // Nombre
      "frecuency": "60",                // Frecuencia de muestreo
      "lat": "-33.456",                 // Latitud (null si no tiene GPS)
      "lon": "-70.648",                 // Longitud (null si no tiene GPS)
      "active": true,                   // true = days_not_connection == 0
      "project_id": 22,                 // ID del proyecto
      "project_name": "Comasa",         // Nombre del proyecto
      "client_name": "Comasa",          // Nombre del cliente
      "provider": "novus",              // Proveedor: twin / nettra / novus / null
      "is_telemetry": true,             // Telemetría activa
      "config_data": {
        "variables": ["CAUDAL", "TOTALIZADO", "NIVEL"]  // Variables configuradas
      },
      "dga": {
        "code_dga": "OB-0902-45",       // Código obra DGA
        "type_dga": "SUBTERRANEO",      // Tipo: SUBTERRANEO / SUPERFICIAL
        "send_dga": true                // Envío a DGA activo
      },
      "latest_telemetry": {             // ÚLTIMO registro de telemetría
        "date_time_medition": "2026-05-09T04:00:00+00:00", // Fecha última medición
        "flow": "20.07",                // Caudal en L/s
        "total": "0",                   // Totalizador en m³
        "nivel": "0.00",                // Nivel en metros
        "water_table": "42.00",         // Nivel freático en metros
        "is_error": false,              // Último registro tiene error
        "days_not_connection": 0        // Días sin conexión
      },
      "alerts_count": 0                 // Notificaciones activas del punto
    }
  ],
  "total_points": 191,     // Total de puntos
  "active_points": 161,    // Puntos activos (sin desconexión)
  "points_with_alerts": 50 // Puntos con al menos 1 alerta
}
```

---

## 🔍 5. DETALLE DE UN PUNTO

```http
GET /api/ik/point/<id>/summary/
Authorization: Token <token>
```

**Para qué sirve:** Cuando el usuario selecciona un punto del dropdown y quiere ver su resumen completo.  
**Permisos:** Solo si es owner, viewer, o admin.

**Respuesta:**
```json
{
  "id": 1,
  "title": "PC Descarga",
  "frecuency": "1",
  "lat": null,
  "lon": null,
  "active": true,
  "project_id": 1,
  "project_name": "SMA",
  "client_name": "Lecheria Valle Verde",
  "provider": "twin",
  "is_telemetry": true,
  "config_data": {
    "variables": ["CAUDAL", "TOTALIZADO"]
  },
  "dga": {
    "code_dga": "7511",
    "type_dga": "SUPERFICIAL",
    "send_dga": true
  },
  "latest_telemetry": {
    "date_time_medition": "2026-05-09T05:00:00+00:00",
    "flow": "10.70",
    "total": "710846",
    "nivel": "0.00",
    "water_table": "0.00",
    "is_error": false,
    "days_not_connection": 0
  },
  "alerts_count": 3
}
```

**404:** Si el punto no existe o el usuario no tiene permisos.

---

## 📅 6. CALENDARIO HISTÓRICO POR PUNTO

```http
GET /api/ik/point/<id>/calendar/?days=7
Authorization: Token <token>
```

**Para qué sirve:** Mostrar un calendario/gráfico de los últimos N días con consumo, caudal promedio y nivel freático.  
**Query params:** `days` — días hacia atrás (default: 7, min: 1, max: 30).

**Dinámico:** Solo incluye los campos que correspondan a las variables del punto.

**Respuesta (punto con CAUDAL + NIVEL):**
```json
{
  "point_id": 77,
  "point_title": "P 2",
  "project_name": "Comasa",
  "client_name": "Comasa",
  "variables": ["TOTALIZADO", "CAUDAL", "NIVEL"],  // Variables activas del punto
  "days": 3,
  "start_date": "2026-05-07",    // Primer día del rango
  "end_date": "2026-05-09",      // Último día del rango
  "calendar": [
    {
      "date": "2026-05-07",                  // Fecha del día
      "date_formatted": "Jue 7 May",         // Fecha corta legible
      "has_data": true,                      // true = hubo registros este día
      "consumption_m3": 0.0,                 // Consumo del día en m³ (suma de total_diff)
      "records_count": 24,                   // Cantidad de registros del día
      "first_record": "2026-05-07T04:00:00+00:00",  // Primer registro del día
      "last_record": "2026-05-08T03:00:00+00:00",   // Último registro del día
      "variables_present": ["TOTALIZADO", "CAUDAL", "NIVEL"],
      "avg_flow_lps": 13.65,     // Caudal promedio del día (L/s) - solo si tiene CAUDAL
      "max_flow_lps": 28.91,     // Caudal máximo del día (L/s) - solo si tiene CAUDAL
      "avg_nivel_m": 5.98,       // Nivel promedio del día (m) - solo si tiene NIVEL
      "avg_water_table_m": 36.02 // Nivel freático promedio (m) - solo si tiene NIVEL o TOTALIZADO
    }
  ]
}
```

**Respuesta (punto solo con CAUDAL, sin NIVEL):**
```json
{
  "point_id": 1,
  "point_title": "PC Descarga",
  "variables": ["TOTALIZADO", "CAUDAL"],
  "calendar": [
    {
      "date": "2026-05-08",
      "has_data": true,
      "consumption_m3": 0.0,
      "records_count": 1440,
      "avg_flow_lps": 8.62,     // ✅ Aparece porque tiene CAUDAL
      "max_flow_lps": 22.93
      // ❌ NO aparece avg_nivel_m porque no tiene NIVEL
    }
  ]
}
```

**Tabla de campos dinámicos:**

| Variable del punto | Campos que aparecen en el día |
|-------------------|------------------------------|
| `CAUDAL` o `CAUDAL_PROMEDIO` | `avg_flow_lps`, `max_flow_lps` |
| `NIVEL` | `avg_nivel_m` |
| `NIVEL` o `TOTALIZADO` | `avg_water_table_m` |

**Campos SIEMPRE presentes:** `date`, `date_formatted`, `has_data`, `consumption_m3`, `records_count`, `first_record`, `last_record`, `variables_present`.

---

## 📁 7. ARCHIVOS (Documentos del punto)

```http
GET /api/file_catchment/?point_catchment=<id>
Authorization: Token <token>
```

**Respuesta:**
```json
[
  {
    "id": 1,
    "point_catchment": 42,
    "type_file": 3,                    // ID de la categoría
    "name": "Certificado 2025",
    "file": "/media/files_catchment/certificado_2025.pdf",
    "description": "Certificado de calibración",
    "is_active": true,
    "created": "2025-01-01T00:00:00-03:00"
  }
]
```

**Para descargar:** Concatenar `https://api.smarthydro.app` + `file` field.

**Categorías:**
```http
GET /api/type_file_catchment/
```

---

## 🔔 8. ALERTAS

```http
GET /api/notifications_catchment/?point_catchment=<id>
Authorization: Token <token>
```

**Respuesta:** Lista de notificaciones del punto.

---

## 🏥 9. HEALTH CHECK (sin auth)

```http
GET /health/
```

Devuelve `200 OK` si Django responde.

---

*Documento actualizado el 2026-05-09 — Listo para copiar y pegar*
