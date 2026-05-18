# Plan de Migración de Alertas — Fases A/B/C

> **Estado:** En diseño  
> **Ambiente:** Producción activa — CAUTELA MÁXIMA  
> **Regla de oro:** Nunca eliminar legacy hasta que la nueva fase esté 100% validada.

---

## 🎯 Objetivo

Sacar las alertas del código (hardcodeadas en `google_chat.py`, `dga_mayor_hourly.py`, runners) y ponerlas en la base de datos como `AlertRule` configurables. Separar claramente:

| Responsabilidad | Sistema |
|---|---|
| Alertas umbral, no-data, webhook | **Nuevo subsistema** (`AlertRule` / `AlertChannel`) |
| Tickets de soporte (Kanban) | **Legacy** (`NotificationsCatchment`) |
| Eventos automáticos (reinicios, errores) | **`SystemEvent`** |

---

## 🛡️ Estrategia de cero downtime

1. **Aditivo siempre:** Solo agregar campos/modelos. Nunca modificar tablas legacy.
2. **Feature flags:** Cada fase se activa con una variable de entorno o flag en DB.
3. **Dry-run obligatorio:** Todo corre en paralelo primero; el legacy sigue siendo la fuente de verdad.
4. **Rollback instantáneo:** Si algo falla, desactivar el flag vuelve al comportamiento anterior.

---

## 📋 FASE A — `severity` en `AlertRule` + alertas globales

### Alcance
- Agregar campo `severity` a `AlertRule` (INFO/WARNING/ALERT/CRITICAL).
- Permitir `point_catchment=None` en el motor para alertas globales.
- Activar validación de `clean()` en serializers DRF.

### Cambios técnicos
1. **Migración `0040`** — `AlertRule.severity` (CharField, choices, default="WARNING").
2. **Motor** — `_evaluate_rule()` soporta `point_catchment=None` para `NO_DATA` y `SCHEDULED_REPORT` globales.
3. **Serializers** — `AlertRuleWriteSerializer` incluye `severity`.
4. **Admin** — Columna `severity` visible.

### Validación
- Crear regla global de prueba (sin punto).
- Verificar que el motor la evalúa en dry-run sin errores.
- Verificar que el admin la muestra.

### Riesgo: **NULO** (campo aditivo opcional).

---

## 📋 FASE B — Migrar alertas hardcodeadas a BD

### Alcance
Convertir estas alertas de código a `AlertRule` + `AlertChannel`:

| Alerta hardcodeada | Tipo nuevo | Canal sugerido |
|---|---|---|
| Punto desconectado (`check_and_notify_disconnection`) | `NO_DATA` | `GOOGLE_CHAT` |
| Punto reconectado (`check_and_notify_reconnection`) | `SystemEvent` + opcional `SCHEDULED_REPORT` | `GOOGLE_CHAT` |
| Caudal autorizado DGA superado | `THRESHOLD_MAX` | `EMAIL` (DGA) |
| Salto masivo bloqueado | `SystemEvent` (ya existe) | — |
| Error de medición | `SystemEvent` (ya existe) | — |

### Cambios técnicos
1. **Script de población** — Crear `AlertRule` predefinidas para cada punto con caudal DGA.
2. **Motor** — Extender `_evaluate_no_data` para que una regla global evalúe TODOS los puntos.
3. **Dispatcher** — Enviar a webhook de Google Chat usando la URL configurada en `AlertChannel.destination`.
4. **Feature flag** — `ALERTS_USE_NEW_DISCONNECT=true` activa la versión nueva; `false` usa `google_chat.py`.

### Validación
- Shadow mode: nueva regla corre en paralelo, legacy sigue enviando.
- Comparar logs: ¿Se detectan las mismas desconexiones?
- Solo cuando coincidan 100%, desactivar legacy.

### Riesgo: **MEDIO** (cambia flujo de notificaciones críticas).

---

## 📋 FASE C — Limpiar `NotificationsCatchment` (solo Kanban)

### Alcance
- Migrar las últimas alertas umbral legacy a `AlertRule`.
- Renombrar/restringir `NotificationsCatchment` para que solo maneje tickets de soporte.
- Eliminar campos de alerta de `NotificationsCatchment` (o marcar deprecated).

### Cambios técnicos
1. **Script final** — Migra todas las `NotificationsCatchment` con `type_alert` a `AlertRule`.
2. **Desactivar legacy** — `alert_evaluator.py` sigue existiendo pero solo evalúa `type_notification=SUPPORT`.
3. **Frontend** — React consume `/api/alert_rules/` para alertas y `/api/notifications_catchment/` para tickets.

### Riesgo: **ALTO** (cambia la API pública del monolito). Requiere coordinación con frontend.

---

## ✅ Checklist antes de activar cada fase

- [ ] Migraciones aplicadas en dev y probadas
- [ ] Tests de regresión pasan (`tests.regression`, `tests.dga`)
- [ ] Dry-run exitoso en producción (sin guardar triggers)
- [ ] Logs revisados: sin errores, sin duplicados
- [ ] Frontend validado (si aplica)
- [ ] Plan de rollback documentado

---

## 🚀 Estado actual

| Fase | Estado |
|---|---|
| A | **Lista para implementar** (cambio aditivo seguro) |
| B | **En diseño** (requiere shadow mode) |
| C | **Pendiente** (requiere coordinación frontend) |
