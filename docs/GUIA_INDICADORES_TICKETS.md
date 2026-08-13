# Guia de Indicadores — Dashboard de Tickets y SLA

> Estado: lista para implementar en frontend
> Endpoints base: `/api/ik/tickets/`, `/api/ik/tickets/stats/`, `/api/ik/tickets/my_desk/`

---

## 1. Indicadores principales (top cards)

| Indicador | Endpoint | Campo | Color / Alerta |
|-----------|----------|-------|----------------|
| **Tickets totales activos** | `GET /api/ik/tickets/stats/` | `total` | Neutro |
| **Tickets abiertos** | `GET /api/ik/tickets/stats/` | `by_status.ABIERTO` | Amarillo si > 20, rojo si > 50 |
| **SLA de resolucion vencido** | `GET /api/ik/tickets/stats/` | `sla_overdue_resolution` | **Rojo** |
| **SLA de respuesta vencido** | `GET /api/ik/tickets/stats/` | `sla_overdue_response` | **Rojo** |
| **Tickets compliance** | `GET /api/ik/tickets/stats/` | `compliance.total` | Naranja si > 0 |
| **Compliance con SLA vencido** | `GET /api/ik/tickets/stats/` | `compliance.sla_overdue_resolution` | **Rojo critico** |

> **Nota (2026-07-31):** Los indicadores SLA vencido (tanto en `/stats/` como en `/dashboard/`)
> solo cuentan tickets en estados abiertos (`ABIERTO`, `EN_ANALISIS`, `ESPERA_CLIENTE`,
> `ESPERA_PROVEEDOR`, `EN_ORDEN_TRABAJO`). Los tickets `RESUELTO`, `CERRADO` y `CANCELADO`
> **nunca** se marcan como SLA vencido, aunque `sla_deadline_*` haya pasado o
> `sla_responded_at`/`sla_resolved_at` estén vacios.
>
> **Criterio de "primera respuesta" (`sla_responded_at`):** se marca con la **primera accion
> de staff** sobre el ticket (comentario no interno, cambio de estado, asignacion, fecha
> agendada o reporte de visita), no solo con comentarios. Si el ticket fue atendido por el
> equipo, la respuesta SLA cuenta como dada aunque no haya comentarios.

### Layout recomendado
```
[Total] [Abiertos] [SLA vencido] [Compliance] [Compliance vencido]
```

---

## 2. Graficos de distribucion

### 2.1 Tickets por estado
- **Tipo:** torta o barras
- **Datos:** `by_status`
- **Valores:** `ABIERTO`, `EN_ANALISIS`, `EN_ORDEN_TRABAJO`, `ESPERA_CLIENTE`, `ESPERA_PROVEEDOR`, `RESUELTO`, `CERRADO`, `CANCELADO`

### 2.2 Tickets por tipo de categoria
- **Tipo:** barras horizontales o donut
- **Datos:** `by_category_type`
- **Valores:** `SOFTWARE`, `HARDWARE`, `COMPLIANCE`, `WORK_ORDER`
- **Destacar:** `COMPLIANCE` en color de alerta

### 2.3 Tickets por prioridad
- **Tipo:** barras
- **Datos:** `by_priority`
- **Valores:** `BAJA`, `MEDIA`, `ALTA`, `CRITICA`
- **Destacar:** `CRITICA` en rojo

### 2.4 Origen de tickets
- **Tipo:** torta
- **Datos:** `by_origin`
- **Valores:** `CLIENTE` vs `INTERNO`
- **Nota:** `INTERNO` son borradores/eventos del sistema

### 2.5 Compliance detalle
- **Tipo:** barras
- **Datos:** `compliance.by_status`
- **Uso:** ver en que estado estan los tickets de cumplimiento

---

## 3. Tabla / Kanban de Mi Escritorio

| Elemento | Endpoint |
|----------|----------|
| **Mis tickets asignados** | `GET /api/ik/tickets/my_desk/?assigned_to=<mi_id>` o filtrar del listado |
| **Tickets de mis categorias** | `GET /api/ik/tickets/my_desk/` |
| **Filtrar por estado** | `GET /api/ik/tickets/my_desk/?status=ABIERTO` |

### Kanban por estado
Columnas: `ABIERTO` → `EN_ANALISIS` → `EN_ORDEN_TRABAJO` → `ESPERA_CLIENTE` → `ESPERA_PROVEEDOR` → `RESUELTO`

---

## 4. Indicadores de SLA

### 4.1 Cumplimiento de SLA
```
% cumplimiento = (1 - (sla_overdue_resolution / tickets_con_sla)) * 100
```

**Como obtener tickets con SLA:**
```http
GET /api/ik/tickets/?origin=CLIENTE
```
y contar los que tienen `sla_deadline_resolution` no nulo.

### 4.2 Proximos a vencer
Tickets cuyo `sla_deadline_resolution` esta entre ahora y las proximas 24h.

**Como obtener:**
```http
GET /api/ik/tickets/?origin=CLIENTE&status=ABIERTO
```
Filtrar en frontend aquellos con deadline dentro de 24h.

### 4.3 Tiempo medio de resolucion
```
Tiempo medio = promedio(resolved_at - created)
```

**Endpoint:**
```http
GET /api/ik/tickets/?status=RESUELTO,CERRADO
```
Calcular en frontend con `resolved_at` y `created`.

> **Pendiente:** se puede agregar un endpoint `/api/ik/tickets/metrics/` que calcule esto en backend.

---

## 5. Indicadores por operador

### 5.1 Tickets asignados por usuario
```http
GET /api/ik/tickets/?assigned_to=<user_id>
```

### 5.2 Tickets por categoria operada
```http
GET /api/ik/tickets/?category_type=HARDWARE
```

### 5.3 Ranking de carga
Mostrar cuantos tickets abiertos tiene cada operador.

> **Pendiente:** se puede agregar endpoint `/api/ik/tickets/stats/by_assignee/`.

---

## 6. Indicadores de compliance (DGA/SMA)

### 6.1 Tickets de compliance
```http
GET /api/ik/tickets/?category_type=COMPLIANCE
```

### 6.2 Compliance con SLA vencido
```http
GET /api/ik/tickets/?category_type=COMPLIANCE&status=ABIERTO
```
Filtrar en frontend por `sla_deadline_resolution < ahora`.

### 6.3 Compliance por subcategoria
```http
GET /api/ik/ticket-categories/?category_type=COMPLIANCE
```
Con las subcategorias, hacer:
```http
GET /api/ik/tickets/?category=<subcategoria_id>
```

### 6.4 Puntos con alertas DGA/SMA
Si queres integrar alertas reales de cumplimiento de puntos (no tickets), usar:
```http
GET /api/ik/compliance/
```

---

## 7. Tendencias en el tiempo

### 7.1 Tickets creados hoy / esta semana / este mes
```http
GET /api/ik/tickets/?created_from=2026-07-03&created_to=2026-07-03
```

### 7.2 Tickets resueltos por dia
```http
GET /api/ik/tickets/?status=RESUELTO,CERRADO&created_from=...&created_to=...
```
Agrupar en frontend por fecha de `resolved_at`.

> **Pendiente:** se puede agregar endpoint `/api/ik/tickets/timeline/` para tendencias.

---

## 8. Propuesta de pantalla de dashboard

```
+--------------------------------------------------+
|  Total  |  Abiertos  |  SLA vencido  |  Compliance  |
+--------------------------------------------------+
|  [Grafico por estado]   |  [Grafico por tipo]     |
+--------------------------------------------------+
|  [Grafico por prioridad] |  [Grafico origen]      |
+--------------------------------------------------+
|  Tabla: SLA vencidos (top 10)                    |
+--------------------------------------------------+
|  Tabla: Compliance con SLA vencido               |
+--------------------------------------------------+
|  Kanban: Mis tickets / Tickets de mis categorias |
+--------------------------------------------------+
```

---

## 9. Endpoints utiles para filtros

| Filtro | Ejemplo |
|--------|---------|
| Por estado | `?status=ABIERTO` |
| Por tipo | `?category_type=HARDWARE` |
| Por categoria | `?category=7` |
| Por prioridad | `?priority=ALTA` |
| Por origen | `?origin=CLIENTE` |
| Por asignado | `?assigned_to=71` |
| Por punto | `?point_id=1` |
| Por proyecto | `?project_id=1` |
| Por fecha | `?created_from=2026-07-01&created_to=2026-07-03` |
| Busqueda | `?search=fuga` |

---

## 10. Mejoras pendientes sugeridas

1. **Endpoint `/api/ik/tickets/metrics/`**: calcular tiempos medios, % cumplimiento SLA, tendencias.
2. **Endpoint `/api/ik/tickets/stats/by_assignee/`**: conteos por usuario asignado.
3. **Endpoint `/api/ik/tickets/timeline/`**: tickets creados/resueltos por dia.
4. **Alertas en UI:** badge rojo en SLA vencido, amarillo en proximo a vencer.
5. **Auto-refresh:** recargar stats cada 5 minutos.
