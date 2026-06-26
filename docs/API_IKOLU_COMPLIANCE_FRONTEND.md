# Guía Frontend — Endpoint `/api/ik/compliance/`

> **Endpoint:** `GET /api/ik/compliance/`  
> **Auth:** Token  
> **Uso:** Dashboard de cumplimiento DGA/SMA (Centro de Control)

---

## 1. ¿Qué resuelve este endpoint?

Te entrega el estado de cumplimiento regulatorio de los puntos del usuario. Incluye:

- Cada punto con sus límites autorizados (caudal + total anual)
- Consumo acumulado del año en curso
- **Conteo de excedencias** (`flow_history.count`) → para badges/modales
- **Conteo de cercanías** (`near_limit_history.count`) → para badges/modales
- **Warning preventivo actual** (`compliance_warning`) → está en riesgo **ahora**
- Último envío exitoso a DGA/SMA (voucher)

> **Cambio reciente:** por defecto se listan los puntos que tienen compliance **configurado** (código DGA o SMA), activos o inactivos, para que el frontend pueda activar/desactivar compliance. Usa `?active_only=true` para mostrar solo los activos. Los puntos sin configuración de compliance no aparecen.
> El detalle de excedencias y cercanías (lista de mediciones) se consulta en endpoints separados de alto rendimiento.

---

## 2. Estructura de respuesta

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "points": [
    {
      "point_id": 1,
      "project_id": 3,
      "point_name": "S3 - Río Claro",
      "client_name": "Cliente A",
      "code": "12345-DGA",
      "compliance_type": ["DGA"],
      "standard": "MAYOR",
      "type_dga": "SUPERFICIAL",
      "compliance_active": true,
      "authorized_flow": 150.0,
      "authorized_total": 50000.0,
      "annual_consumption": 12500.5,
      "pct_consumed": 25.01,
      "flow": 120.5,
      "water_table": 0.0,
      "flow_history": { "count": 5, "has_more": false, "threshold": 150.0 },
      "near_limit_history": { "count": 8, "has_more": false, "threshold": 150.0 },
      "compliance_warning": { "level": "safe" },
      "voucher": "VOUCHER-123456"
    },
    {
      "point_id": 2,
      "project_id": 3,
      "point_name": "Canal Desconectado",
      "client_name": "Cliente A",
      "code": null,
      "compliance_type": [],
      "standard": null,
      "type_dga": null,
      "compliance_active": false,
      "authorized_flow": null,
      "authorized_total": null,
      "annual_consumption": 0.0,
      "pct_consumed": null,
      "flow": 0.0,
      "water_table": 0.0,
      "flow_history": { "count": 0, "has_more": false, "threshold": null },
      "near_limit_history": { "count": 0, "has_more": false, "threshold": null },
      "compliance_warning": { "level": "unknown" },
      "voucher": null
    }
  ]
}
```

---

## 3. Cómo interpretar los 3 pilares de cumplimiento

### A. `flow_history` — Pasado reactivo (conteo)
- **Qué cuenta:** Veces que el caudal **ya superó** el límite autorizado (`flow > authorized_flow`) en los últimos 90 días.
- **Usalo para:** Mostrar un contador rojo en la tabla.
- **Ejemplo UI:**
  - Badge rojo con número 🔴 `5 excedencias`
  - Click abre un modal que consume `GET /api/ik/compliance/<point_id>/flow_history/` para traer la lista paginada de mediciones.

### B. `near_limit_history` — Pasado preventivo (conteo)
- **Qué cuenta:** Veces que el caudal estuvo entre el **90% y 100%** del límite autorizado en los últimos 90 días.
- **Usalo para:** Mostrar cuántas veces "casi se pasó". Es un indicador de comportamiento de riesgo.
- **Ejemplo UI:**
  - Badge naranja/amarillo 🟡 `8 veces cerca del límite`
  - Click abre un modal que consume `GET /api/ik/compliance/<point_id>/near_limit/` para traer la lista paginada.

### C. `compliance_warning` — Estado actual
- **Qué es:** Alerta **preventiva en tiempo real**. No repite lo del historial.
- **Disparadores:**
  - Consumo acumulado ≥ 80% del total autorizado
  - Caudal actual ≥ 90% del límite autorizado (pero sin excederlo)
  - Consumo acumulado ≥ 100% → `critical`
- **Usalo para:** Pintar la fila/card del punto, mostrar banner de alerta, enviar notificación push.

| `level` | Significado | Color sugerido | `status` |
|---------|-------------|----------------|----------|
| `safe` | Todo bien | 🟢 Verde | "Dentro de límites" |
| `warning` | Cerca de superar un límite | 🟡 Amarillo/Naranja | "Cerca de superar límite" |
| `critical` | Ya se superó el total anual | 🔴 Rojo | "Incumplimiento detectado" |
| `unknown` | Faltan datos de configuración | ⚪ Gris | "Sin límites configurados" |

---

## 4. Patrones de UI recomendados

### 4.1 KPIs globales (derivados del listado)

Ya no hay nodo `stats`; puedes calcular KPIs del listado paginado o de todos los puntos (si cargas la primera página grande):

```javascript
const points = response.points;

// Tarjetas de resumen
"Puntos visibles": response.count
"Con compliance activo": points.filter(p => p.compliance_active).length
"Con alertas activas": points.filter(p => p.compliance_warning.level === 'warning').length
"Con incumplimiento": points.filter(p => p.compliance_warning.level === 'critical').length
```

### 4.2 Tabla de puntos

| Punto | Código | Tipo | Consumo | Caudal | Excedencias | Cercanías | Estado |
|-------|--------|------|---------|--------|-------------|-----------|--------|
| S3 | 12345-DGA | DGA | 25% | 120 L/s | 5 | 8 | 🟢 Safe |
| Pozo N | 67890-DGA | DGA | 86% | 48 L/s | 0 | 1 | 🟡 Warning |
| Canal | SMA-001 | SMA | 105% | 210 L/s | 5 | 2 | 🔴 Critical |

**Cómo construir la fila:**
- Nombre: `point_name`
- Consumo: `pct_consumed ? pct_consumed + '%' : '—'`
- Caudal actual: `flow + ' L/s'`
- Excedencias: `flow_history.count` (rojo si > 0)
- Cercanías: `near_limit_history.count` (naranja si > 0)
- Estado: badge según `compliance_warning.level`

### 4.3 Fila expandible / Drawer / Modal

Al hacer click en una fila (o en un badge de excedencias/cercanías), mostrar un drawer/modal que consume los endpoints de detalle:

**Sección Warning Actual**
```
🟡 Cerca de superar límite
→ El consumo acumulado alcanza el 86% del total autorizado (umbral: 80%).
→ Caudal actual (95.5 L/s) está al 95.5% del límite autorizado (100 L/s).
```

**Sección Histórico de Excedencias**
```
GET /api/ik/compliance/<point_id>/flow_history/
🔴 5 excedencias en los últimos 90 días
┌─────────────────────┬───────┐
│ Fecha               │ Caudal│
├─────────────────────┼───────┤
│ 2026-05-25 14:00    │ 250.0 │
│ 2026-05-24 14:00    │ 230.5 │
└─────────────────────┴───────┘
```

**Sección Histórico de Cercanías**
```
GET /api/ik/compliance/<point_id>/near_limit/
🟡 8 veces cerca del límite en los últimos 90 días
┌─────────────────────┬───────┐
│ Fecha               │ Caudal│
├─────────────────────┼───────┤
│ 2026-05-28 10:00    │ 145.0 │
│ 2026-05-27 10:00    │ 148.5 │
└─────────────────────┴───────┘
```

**Sección Último Envío DGA**
```
Último envío: 2026-05-28 14:00
Voucher: VOUCHER-123456
Valores enviados: flow 120.5 | total 45271.0 | water_table 0.0
```

### 4.4 Gráfico de gauges (medidores)

Para cada punto, gauges circulares:
- **% Consumo anual:** `pct_consumed` (rojo si ≥ 100, amarillo si ≥ 80, verde si < 80)
- **% Caudal actual vs límite:** `(flow / authorized_flow) * 100` (amarillo si ≥ 90, rojo si ≥ 100)

### 4.5 Filtros rápidos

**Por backend (query params):**
- "Solo activos" → `?active_only=true`
- "Por estándar" → `?standard=MAYOR` o `?standard=MAYOR,MEDIO`
- "Por nombre/código" → `?search=OB-0702`
- "Con excedencias" → `?order_by=exceedances_desc` (activos primero, luego más excedencias)
- "Cerca del límite" → `?order_by=near_limit_desc`

**Por frontend (derivado del listado):**
- "Solo alertas" → `level === 'warning' || level === 'critical'`
- "Solo críticos" → `level === 'critical'`

---

## 5. Reglas importantes

### No dupliques información
- `flow_history` y `near_limit_history` en el listado son **conteos**. El detalle de mediciones va en los endpoints dedicados.
- `compliance_warning` es **solo para el estado actual** del punto.

### Manejo de `null` / datos faltantes
- `authorized_flow` o `authorized_total` pueden ser `null` → punto sin límites configurados (`level: 'unknown'`)
- `pct_consumed` puede ser `null` → no hay consumo registrado o no hay total autorizado
- `code` puede ser `null` → punto sin compliance activo
- `voucher` puede ser `null` → nunca se ha enviado a DGA/SMA

### Badges de compliance type
- Si `compliance_type` incluye `"DGA"` → badge azul "DGA"
- Si incluye `"SMA"` → badge verde "SMA"
- Si tiene ambos → dos badges

---

## 6. Ejemplo completo de consumo en React (pseudo-código)

```jsx
function ComplianceRow({ point }) {
  const w = point.compliance_warning;

  const colorMap = {
    safe: 'green',
    warning: 'orange',
    critical: 'red',
    unknown: 'gray',
  };

  return (
    <tr style={{ borderLeft: `4px solid ${colorMap[w.level]}` }}>
      <td>{point.point_name}</td>
      <td>{point.code}</td>
      <td>{point.pct_consumed ?? '—'}%</td>
      <td>{point.flow} L/s</td>
      <td>
        {point.flow_history.count > 0 && (
          <Badge color="red">{point.flow_history.count} excedencias</Badge>
        )}
      </td>
      <td>
        {point.near_limit_history.count > 0 && (
          <Badge color="orange">{point.near_limit_history.count} cercanías</Badge>
        )}
      </td>
      <td>
        <Badge color={colorMap[w.level]}>{w.status}</Badge>
      </td>
    </tr>
  );
}
```

---

## 7. Resumen visual

```
┌─────────────────────────────────────────────────────────────┐
│  COMPLIANCE DGA/SMA                                         │
├─────────────────────────────────────────────────────────────┤
│  KPIs: 10 puntos | 2 alertas 🟡 | 1 crítico 🔴             │
├─────────────────────────────────────────────────────────────┤
│  Tabla:                                                     │
│  [Punto] [Consumo] [Caudal] [Excedió] [Casi] [Estado]      │
│  S3      25%       120      5 🔴      8 🟡   🟢 Safe       │
│  Pozo N  86%       48       0         1 🟡   🟡 Warning    │
│  Canal   105%      210      5 🔴      2 🟡   🔴 Critical   │
├─────────────────────────────────────────────────────────────┤
│  Drawer (Pozo N seleccionado):                              │
│  🟡 Cerca de superar límite                                 │
│  → Consumo al 86% (umbral 80%)                              │
│                                                             │
│  🔴 Excedencias: 0                                          │
│  🟡 Cercanías: 1                                            │
│     • 2026-05-20 10:30 — 65.5 L/s                           │
│                                                             │
│  Último envío DGA: 2026-05-27 — VOUCHER-789012              │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Cambios recientes

| Fecha | Cambio |
|-------|--------|
| 2026-06-26 | `/api/ik/compliance/` lista **todos** los puntos por defecto; `?active_only=true` filtra activos. |
| 2026-06-26 | Nuevos endpoints paginados: `/api/ik/compliance/<point_id>/flow_history/` y `/api/ik/compliance/<point_id>/near_limit/`. |
| 2026-06-26 | `flow_history` y `near_limit_history` ahora son `{count, has_more, threshold}`; el detalle se consulta en los endpoints dedicados. |
| 2026-06-01 | `compliance_warning` ahora es preventivo (no repite excedencias). |
| 2026-06-01 | Agregado `near_limit_history` para contar veces entre 90%-100% del límite. |
