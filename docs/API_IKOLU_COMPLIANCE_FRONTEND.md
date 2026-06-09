# Guía Frontend — Endpoint `/api/ik/compliance/`

> **Endpoint:** `GET /api/ik/compliance/`  
> **Auth:** Token  
> **Uso:** Dashboard de cumplimiento DGA/SMA (Centro de Control)

---

## 1. ¿Qué resuelve este endpoint?

Te entrega **todo lo que necesitas** para mostrar el estado de cumplimiento regulatorio de los puntos del usuario en una sola llamada. Incluye:

- Totales y filtros agregados (`stats`)
- Cada punto con sus límites autorizados (caudal + total anual)
- Consumo acumulado del año en curso
- **Historial de excedencias** (`flow_history`) → ya superó el límite
- **Historial de cercanías** (`near_limit_history`) → estuvo a nada de superarlo
- **Warning preventivo actual** (`compliance_warning`) → está en riesgo **ahora**
- Último envío exitoso a DGA/SMA (voucher, fecha, valores)

---

## 2. Estructura de respuesta

```json
{
  "stats": {
    "total": 10,
    "with_warnings": 2,
    "with_critical": 1,
    "by_standard": { "MAYOR": 8, "MENOR": 2 },
    "by_type": { "SUPERFICIAL": 6, "SUBTERRANEA": 4 }
  },
  "points": [
    {
      "point_id": 1,
      "point_name": "S3 - Río Claro",
      "code": "12345-DGA",
      "compliance_type": ["DGA"],
      "standard": "MAYOR",
      "type_dga": "SUPERFICIAL",
      "send_dga": true,
      "send_sma": false,
      "authorized_flow": 150.0,
      "authorized_total": 50000.0,
      "annual_consumption": 12500.5,
      "pct_consumed": 25.01,
      "flow_history": { "count": 5, "threshold": 150.0, "measurements": [...] },
      "near_limit_history": { "count": 8, "threshold": 150.0, "measurements": [...] },
      "compliance_warning": {
        "level": "safe",
        "status": "Dentro de límites",
        "pct_consumed": 25.01,
        "threshold_pct": 80.0,
        "messages": ["Consumo dentro de límites (25.01% del total autorizado)."]
      },
      "last_sent_at": "2026-05-28T14:00:00",
      "voucher": "VOUCHER-123456",
      "flow": 120.5,
      "water_table": 0.0,
      "total": 45271.0
    }
  ]
}
```

---

## 3. Cómo interpretar los 3 pilares de cumplimiento

### A. `flow_history` — Pasado reactivo
- **Qué cuenta:** Veces que el caudal **ya superó** el límite autorizado (`flow > authorized_flow`) este año.
- **Usalo para:** Mostrar un contador rojo, una tabla de "excedencias", o un gráfico de eventos pasados.
- **Ejemplo UI:**
  - Badge rojo con número 🔴 `5 excedencias`
  - Click expande tabla con fecha/valor de cada una (`measurements`)

### B. `near_limit_history` — Pasado preventivo
- **Qué cuenta:** Veces que el caudal estuvo entre el **90% y 100%** del límite autorizado este año.
- **Usalo para:** Mostrar cuántas veces "casi se pasó". Es un indicador de comportamiento de riesgo.
- **Ejemplo UI:**
  - Badge naranja/amarillo 🟡 `8 veces cerca del límite`
  - Click expande tabla con las mediciones (`measurements`)

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

### 4.1 KPIs globales (usando `stats`)

```javascript
const stats = response.stats;

// Tarjetas de resumen
"Puntos con compliance": stats.total
"Con alertas activas": stats.with_warnings       // amarillo
"Con incumplimiento": stats.with_critical        // rojo
"Estándar Mayor": stats.by_standard.MAYOR || 0
"Captación Superficial": stats.by_type.SUPERFICIAL || 0
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

Al hacer click en una fila, mostrar:

**Sección Warning Actual**
```
🟡 Cerca de superar límite
→ El consumo acumulado alcanza el 86% del total autorizado (umbral: 80%).
→ Caudal actual (95.5 L/s) está al 95.5% del límite autorizado (100 L/s).
```

**Sección Histórico de Excedencias**
```
🔴 5 excedencias en 2026
┌─────────────────────┬───────┐
│ Fecha               │ Caudal│
├─────────────────────┼───────┤
│ 2026-05-25 14:00    │ 250.0 │
│ 2026-05-24 14:00    │ 230.5 │
└─────────────────────┴───────┘
```

**Sección Histórico de Cercanías**
```
🟡 8 veces cerca del límite en 2026
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

Usa `compliance_warning.level` para filtros:
- "Ver todo"
- "Solo alertas" → `level === 'warning' || level === 'critical'`
- "Solo críticos" → `level === 'critical'`

---

## 5. Reglas importantes

### No dupliques información
- `flow_history` y `near_limit_history` ya traen el detalle. **No repitas** esos conteos en el `compliance_warning`.
- `compliance_warning` es **solo para el estado actual** del punto.

### Manejo de `null` / datos faltantes
- `authorized_flow` o `authorized_total` pueden ser `null` → punto sin límites configurados (`level: 'unknown'`)
- `pct_consumed` puede ser `null` → no hay consumo registrado o no hay total autorizado
- `last_sent_at` puede ser `null` → nunca se ha enviado a DGA/SMA

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
| 2026-06-01 | `compliance_warning` ahora es preventivo (no repite excedencias) |
| 2026-06-01 | Agregado `near_limit_history` para contar veces entre 90%-100% del límite |
| 2026-06-01 | `stats` incluye `with_warnings` y `with_critical` |
