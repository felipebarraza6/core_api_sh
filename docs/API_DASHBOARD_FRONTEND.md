# 📊 Dashboard Stats — Guía para Frontend

> **Endpoint:** `GET /api/ik/dashboard_stats/`  
> **Auth:** Token (`Authorization: Token <token>`)  
> **Content-Type:** `application/json`  
> **Throttle:** 60 req/minuto por usuario

---

## 1. Resumen

Este endpoint entrega **todo lo que necesita el Centro de Control (Dashboard)** en una sola llamada:

- Conteo de puntos (total, con telemetría, con GPS, con compliance)
- Estado de conexión de hoy
- Histórico de los últimos 7 días por punto (consumo, caudal, nivel)
- Warnings/alertas recientes por punto

> **Nota:** El resumen detallado de compliance DGA/SMA ahora viene de un endpoint separado: `GET /api/ik/compliance/`. Ver [API_IKOLU_ENDPOINTS.md](API_IKOLU_ENDPOINTS.md) para más detalles.

**Tiempo de respuesta:** ~0.5s para 8 puntos, ~0.8s para 40 puntos.

---

## 2. Request

```http
GET /api/ik/dashboard_stats/
Authorization: Token 7cea838e314df24633740df24d7d3e0d08d56f6c
Accept: application/json
```

Sin query params. La respuesta siempre es completa para el usuario autenticado.

---

## 3. Response — Estructura

```json
{
  "points": { ... },
  "status_today": { ... },
  "last_7": { ... }
}
```

### 3.1 `points`
Contadores globales del usuario.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `total` | `int` | Total de puntos que ve el usuario (owner + viewer) |
| `with_telemetry` | `int` | Puntos que tienes telemetría activa |
| `with_gps` | `int` | Puntos con lat/lon configurados |
| `with_compliance` | `int` | Puntos con envío DGA o SMA activo |

### 3.2 `status_today`
Conexiones del día actual.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `connected` | `int` | Puntos con al menos 1 medición hoy |
| `disconnected` | `int` | Puntos con telemetría pero sin mediciones hoy |

### 3.3 `last_7`
Objeto cuyas **claves son los nombres de los puntos** (`point_name`). Cada valor contiene el resumen semanal + breakdown diario.

```json
"P4": {
  "point_id": 4,
  "title": "P4",
  "d1": 120.5,
  "d3": 85.0,
  "total_m3": 14911.0,
  "total_measurements_week": 150,
  "avg_flow_week": 113.38,
  "avg_level_week": 33.44,
  "days": [ ... ]
}
```

#### Rollup semanal
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `total_m3` | `float` | Suma de consumos de los 7 días |
| `total_measurements_week` | `int` | Total de mediciones en la semana |
| `avg_flow_week` | `float\|null` | Promedio global de caudal de **todas** las mediciones de la semana |
| `avg_level_week` | `float\|null` | Promedio global de nivel de **todas** las mediciones de la semana |
| `d1` | `float\|null` | Profundidad del pozo (m). `null` si no está configurada o es 0 |
| `d3` | `float\|null` | Posicionamiento del nivel (m). `null` si no está configurado o es 0 |

#### Breakdown diario (`days`)
Array de 7 elementos, del más antiguo al más reciente.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `date` | `string` | Fecha en formato `YYYY-MM-DD` |
| `consumption` | `float` | Suma de `total_diff` del día. Puede ser negativo si hubo reset/salto |
| `measurements_count` | `int` | Cantidad de mediciones ese día |
| `has_data` | `boolean` | `true` si ese día tuvo al menos 1 medición |
| `avg_flow` | `float\|null` | Caudal promedio del día sanitizado a `≥0.0`. `null` si no hay datos ese día o el punto no tiene caudal |
| `avg_level` | `float\|null` | Nivel promedio del día sanitizado a `≥0.0`. `null` si no hay datos ese día o el punto no tiene nivel |
| `warnings` | `array` | Warnings/eventos de ese día específico. Vacío si no hay |

#### Warnings dentro de cada día
Cada objeto del array `days` incluye un array `warnings` con los eventos ocurridos **exactamente ese día** (reset de contador, alertas del sistema, etc.). Ordenados del más reciente al más antiguo dentro del día.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `time` | `string` | ISO 8601 del evento |
| `type` | `string` | Tipo: `"RESET"` o el tipo de notificación |
| `severity` | `string` | Nivel: `"WARNING"`, `"ERROR"`, etc. |
| `message` | `string` | Mensaje en español. Ej: `"Salto masivo bloqueado (total: 487991.000)"` |

**Tipos de reset posibles (mensajes en español):**
- `Salto masivo bloqueado`
- `Reset a 0`
- `Reset parcial rechazado (sin evidencia de desconexión)`
- `Reset por reconexión`

---

## 4. Ejemplo completo (Iansa — 8 puntos)

```json
{
  "points": {
    "total": 8,
    "with_telemetry": 8,
    "with_gps": 0,
    "with_compliance": 8
  },
  "status_today": {
    "connected": 8,
    "disconnected": 0
  },
  "last_7": {
    "P4": {
      "point_id": 4,
      "title": "P4",
      "d1": 120.5,
      "d3": 85.0,
      "total_m3": 14911.0,
      "total_measurements_week": 150,
      "avg_flow_week": 113.38,
      "avg_level_week": 33.44,
      "days": [
        {
          "date": "2026-05-19",
          "consumption": 2126.0,
          "measurements_count": 20,
          "has_data": true,
          "avg_flow": 23.78,
          "avg_level": 44.8,
          "warnings": []
        },
        {
          "date": "2026-05-20",
          "consumption": 2315.0,
          "measurements_count": 24,
          "has_data": true,
          "avg_flow": 126.21,
          "avg_level": 33.05,
          "warnings": []
        },
        {
          "date": "2026-05-21",
          "consumption": 2144.0,
          "measurements_count": 24,
          "has_data": true,
          "avg_flow": 353.54,
          "avg_level": 0.0,
          "warnings": []
        },
        {
          "date": "2026-05-22",
          "consumption": 1938.0,
          "measurements_count": 21,
          "has_data": true,
          "avg_flow": 197.12,
          "avg_level": 16.47,
          "warnings": [
            {
              "time": "2026-05-22T16:06:41.227853+00:00",
              "type": "RESET",
              "severity": "WARNING",
              "message": "Salto masivo bloqueado (total: 477604.000)"
            }
          ]
        },
        {
          "date": "2026-05-23",
          "consumption": 2590.0,
          "measurements_count": 24,
          "has_data": true,
          "avg_flow": 35.57,
          "avg_level": 48.39,
          "warnings": []
        },
        {
          "date": "2026-05-24",
          "consumption": 2658.0,
          "measurements_count": 20,
          "has_data": true,
          "avg_flow": 33.13,
          "avg_level": 48.32,
          "warnings": [
            {
              "time": "2026-05-24T22:06:43.328170+00:00",
              "type": "RESET",
              "severity": "WARNING",
              "message": "Salto masivo bloqueado (total: 487991.000)"
            }
          ]
        },
        {
          "date": "2026-05-25",
          "consumption": 1140.0,
          "measurements_count": 17,
          "has_data": true,
          "avg_flow": 24.29,
          "avg_level": 43.05,
          "warnings": []
        }
      ]
    },
    "P2": {
      "point_id": 2,
      "title": "P2",
      "d1": null,
      "d3": null,
      "total_m3": 1457.0,
      "total_measurements_week": 150,
      "avg_flow_week": null,
      "avg_level_week": null,
      "days": [
        {
          "date": "2026-05-19",
          "consumption": 0.0,
          "measurements_count": 16,
          "has_data": true,
          "avg_flow": null,
          "avg_level": null,
          "warnings": []
        },
        {
          "date": "2026-05-20",
          "consumption": 155.0,
          "measurements_count": 24,
          "has_data": true,
          "avg_flow": null,
          "avg_level": null,
          "warnings": []
        },
        {
          "date": "2026-05-21",
          "consumption": 0.0,
          "measurements_count": 24,
          "has_data": true,
          "avg_flow": null,
          "avg_level": null,
          "warnings": []
        },
        {
          "date": "2026-05-22",
          "consumption": 0.0,
          "measurements_count": 24,
          "has_data": true,
          "avg_flow": null,
          "avg_level": null,
          "warnings": []
        },
        {
          "date": "2026-05-23",
          "consumption": 0.0,
          "measurements_count": 24,
          "has_data": true,
          "avg_flow": null,
          "avg_level": null,
          "warnings": []
        },
        {
          "date": "2026-05-24",
          "consumption": 0.0,
          "measurements_count": 21,
          "has_data": true,
          "avg_flow": null,
          "avg_level": null,
          "warnings": []
        },
        {
          "date": "2026-05-25",
          "consumption": 1302.0,
          "measurements_count": 17,
          "has_data": true,
          "avg_flow": null,
          "avg_level": null,
          "warnings": [
            {
              "time": "2026-05-25T16:02:25.053336+00:00",
              "type": "RESET",
              "severity": "WARNING",
              "message": "Salto masivo bloqueado (total: 13925.000)"
            }
          ]
        }
      ]
    }
  }
}
```

---

## 5. Notas importantes para el Frontend

### 5.1 Keys dinámicas y orden
`last_7` usa el **nombre del punto** como key, no el ID.  
**El orden es alfabético ascendente** (A-Z) por nombre del punto: `LDA`, `Norte`, `P2`, `P3`, `P4`, `P5`, `P6`, `Sur`.

Ejemplo:

```js
// ❌ No funciona
const p4Data = data.last_7[2];

// ✅ Funciona
const p4Data = data.last_7["P4"];
```

Si necesitas iterar todos los puntos:

```js
Object.entries(data.last_7).forEach(([pointName, weekData]) => {
  console.log(pointName, weekData.total_m3);
});
```

### 5.2 Valores `null` vs `0.0`
- **`null`** → El punto no tiene esa variable configurada, **o** ese día no hubo mediciones (`has_data: false`).
- **`0.0`** → Sí hay datos y el promedio dio cero (o el valor sanitizado de una variación eléctrica negativa).

```json
"avg_flow_week": null,
"avg_flow": null
```

**Ejemplo:** P2 solo tiene `TOTALIZADO`, por eso `avg_flow` y `avg_level` son `null`.

### 5.3 Consumos negativos
El campo `consumption` refleja la suma real de `total_diff`. Si hubo un reset o salto masivo, puede ser negativo. El frontend debe estar preparado para mostrarlos (o filtrarlos si prefieren ocultarlos).

```json
"consumption": -190316.0
```

> **Nota:** Caudal y nivel nunca se entregan negativos. Si una medición individual es negativa (variación eléctrica), se sanitiza a `0.0` antes de promediar.

### 5.4 Warnings vacíos
Si un día no tiene warnings, su array `warnings` viene vacío:

```json
{
  "date": "2026-05-23",
  "consumption": 2590.0,
  "measurements_count": 24,
  "has_data": true,
  "avg_flow": 35.57,
  "avg_level": 48.39,
  "warnings": []
}
```

### 5.5 Fechas en `last_7`
Siempre son 7 días, en **orden cronológico** (del más antiguo al más reciente):
- Índice 0 = hace 6 días
- Índice 6 = hoy

Esto facilita graficar directamente el array sin tener que invertirlo en el frontend.

---

## 6. Diagrama de flujo sugerido (Frontend)

```
1. Login → obtener Token
2. GET /api/ik/dashboard_stats/
3. Renderizar:
   ├─ Tarjetas KPI (points.total, status_today.connected, etc.)
   ├─ Gráfico de barras: last_7[point].days[].consumption
   ├─ Gráfico de líneas: last_7[point].days[].avg_flow / avg_level
   └─ Panel de warnings: last_7[point].days[i].warnings
```

---

## 7. Errores comunes

| Status | Significado |
|--------|-------------|
| `401 Unauthorized` | Token inválido o no enviado |
| `429 Too Many Requests` | Throttling excedido (60 req/min) |
| `200 OK` | Siempre devuelve 200 con el JSON completo (incluso si el usuario no tiene puntos) |

---

**Última actualización:** 2026-05-25  
**Versión del endpoint:** v2 (optimizado)
