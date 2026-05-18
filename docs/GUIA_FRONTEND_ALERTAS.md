# Guía Frontend — Alertas con Múltiples Emails y Stats

## 1. Crear / Editar una Alerta

### Endpoint
```
POST /api/notifications_catchment/
PUT  /api/notifications_catchment/{id}/
```

### Payload (ejemplo)

```json
{
  "title": "Alerta Nivel Alto",
  "message": "Descripción opcional de la alerta",
  "emails": ["felipebarraza@smarthydro.cl", "soporte@smarthydro.cl"],
  "type_variable": "NIVEL",
  "type_alert": "MAX",
  "value": 50,
  "type_notification": "ALERT",
  "is_active": true,
  "point_catchment": 64
}
```

### Campos clave

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `emails` | `array[string]` | **NUEVO.** Lista de emails destinatarios. Ej: `["a@x.com", "b@x.com"]` |
| `message` | `string` | Vuelve a ser el mensaje descriptivo. Ya no sirve como email. |
| `type_variable` | `string` | `"NIVEL"`, `"CAUDAL"`, `"TOTALIZADO"`, `"CAUDAL PROMEDIO"`, `"TODOS"` |
| `type_alert` | `string` | `"MAX"`, `"MIN"`, `"EQUALS"` |
| `value` | `integer` | Umbral numérico |
| `point_catchment` | `integer` | ID del punto de captación |

> **Nota:** El campo `emails` es un **array de strings**, no un string separado por comas.

---

## 2. Ver una Alerta (con Stats)

### Endpoint
```
GET /api/notifications_catchment/{id}/
```

### Respuesta (simplificada)

```json
{
  "id": 980,
  "title": "Freatico",
  "emails": ["andresnunez@smarthydro.cl"],
  "type_variable": "NIVEL",
  "type_alert": "MAX",
  "value": 6,
  "is_active": true,
  "stats": {
    "total_triggers": 22,
    "first_trigger": "2026-04-28T16:50:06+00:00",
    "last_trigger": "2026-04-29T13:40:08+00:00",
    "triggers_last_24h": 0,
    "triggers_last_7d": 0,
    "triggers_last_30d": 22,
    "active_days": 2,
    "avg_hours_between_triggers": 0.99,
    "peak_hour": { "hour": 15, "count": 2 },
    "last_measured_value": 16.2,
    "history_limit_days": 30,
    "history_limit_records": 50,
    "trigger_history": [
      {
        "triggered_at": "2026-04-28T16:50:06+00:00",
        "response_text": "ALERTA DISPARADA - Variable: NIVEL | Condicion: MAX 6 | Valor medido: 16.3 | Diferencia: 10.30 | Fecha medicion: 2026-04-28 12:00:00",
        "measured_value": 16.3,
        "matched_interaction": {
          "id": 2838289,
          "date_time_medition": "2026-04-28T17:00:00Z",
          "nivel": 27.0,
          "flow": 0.0,
          "total": "177312",
          "pulses": 46264,
          "total_diff": 31,
          "total_today_diff": 648,
          "days_not_conection": 0,
          "is_error": false
        }
      }
    ]
  }
}
```

### Objeto `stats` explicado

| Campo | Tipo | Para qué sirve |
|-------|------|----------------|
| `total_triggers` | `int` | Total histórico de disparos |
| `first_trigger` | `string` (ISO) | Primera vez que sonó |
| `last_trigger` | `string` (ISO) | Última vez que sonó |
| `triggers_last_24h` | `int` | Disparos últimas 24h |
| `triggers_last_7d` | `int` | Disparos últimos 7 días |
| `triggers_last_30d` | `int` | Disparos últimos 30 días |
| `active_days` | `int` | Días distintos con al menos un disparo |
| `avg_hours_between_triggers` | `float` | Promedio de horas entre disparos |
| `peak_hour` | `object` | Hora del día con más disparos (`hour`, `count`) |
| `last_measured_value` | `float` | Último valor que disparó la alerta |
| `history_limit_days` | `int` | Siempre `30`. El historial solo trae últimos 30 días |
| `history_limit_records` | `int` | Siempre `50`. Máximo 50 registros en el array |
| `trigger_history` | `array` | **Listado de disparos con mediciones completas** |

### Elementos de `trigger_history`

| Campo | Descripción |
|-------|-------------|
| `triggered_at` | Fecha exacta del disparo |
| `response_text` | Texto completo del disparo (parseable) |
| `measured_value` | Valor numérico que provocó el disparo |
| `matched_interaction` | **Registro completo de telemetría** en ese momento: `nivel`, `flow`, `total`, `pulses`, `total_diff`, etc. |

---

## 3. Alertas Legacy (compatibilidad)

Las alertas creadas **antes del cambio** siguen funcionando:
- Si tienen email en el campo `message`, el backend lo lee como fallback.
- En la migración de datos, se copiaron los emails de `message` al array `emails`.
- Al editar una alerta legacy, el front debería mover el email a `emails` y dejar `message` como texto descriptivo.

---

## 4. Ideas para el Dashboard

Con el objeto `stats` puedes armar fácilmente:

### KPIs (tarjetas)
- **Total disparos:** `stats.total_triggers`
- **Disparos hoy:** `stats.triggers_last_24h`
- **Disparos esta semana:** `stats.triggers_last_7d`
- **Disparos este mes:** `stats.triggers_last_30d`
- **Promedio entre disparos:** `stats.avg_hours_between_triggers` + " horas"

### Gráficos
- **Línea de tiempo:** usar `trigger_history[].triggered_at` vs `trigger_history[].measured_value`
- **Distribución por hora:** `stats.peak_hour` muestra la hora más crítica
- **Barras por día:** contar `trigger_history` agrupado por día

### Tabla de historial
- Columnas: Fecha (`triggered_at`), Valor (`measured_value`), Nivel (`matched_interaction.nivel`), Caudal (`matched_interaction.flow`), Total (`matched_interaction.total`)

---

## 5. Resumen de cambios para el dev front

| Antes | Ahora |
|-------|-------|
| `message` guardaba el email | `message` es descripción libre |
| No había campo de emails | `emails` es array `["a@x.com"]` |
| GET solo retornaba la alerta | GET (retrieve) incluye `stats` + `trigger_history` |
| No había historial de mediciones | `trigger_history` trae cada disparo con su medición completa |
