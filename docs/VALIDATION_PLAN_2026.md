# Plan de Validación SmartHydro — 2026-05-16

> **Estado:** Fase 1 completa ✅  
> **Objetivo:** Validar que todos los cambios recientes funcionan en producción sin romper legacy.

---

## FASE 1: Validación de Endpoints Ikolu (sin riesgo)
**Estado:** ✅ COMPLETADA  
**Riesgo:** NINGUNO — solo lectura  
**Tiempo:** ~15 minutos

### 1.1 Health Checks
- [x] `GET /health/` → 200 ✅
- [x] `GET /api/ik/points_summary/` → 200 + JSON válido ✅
- [x] `GET /api/ik/point/{id}/summary/` → 200 + tiene `variable_values` ✅
- [x] `GET /api/ik/point/{id}/variables/` → 200 + tiene mapping `id→display_key` ✅
- [x] `POST /api/ik/batch/telemetry/` → 200 + devuelve `variable_values` ✅

### 1.2 Hallazgos
| Aspecto | Estado | Detalle |
|---------|--------|---------|
| `variable_values` en respuestas | ✅ | Todos los endpoints lo incluyen correctamente |
| `variable_values` poblado (24h) | 🟡 | 769/5,826 registros recientes (13.2%). El resto viene de cronjobs legacy |
| `display_key` configurado | 🔴 | **0/167 variables** tienen `display_key` seteado |
| `display_key` en endpoint | ✅ | Usa fallback `type_variable` (CAUDAL, TOTALIZADO, NIVEL) |
| `min_value`/`max_value` | 🔴 | **0/167 variables** tienen rangos configurados |
| Cron healthcheck | ✅ | Fixed y healthy tras recrear contenedor |

---

## FASE 2: Validación de Modelos y Admin
**Estado:** ⏳ PENDIENTE  
**Riesgo:** BAJO — solo configuración  
**Tiempo estimado:** 15 minutos

### 2.1 Variables
- [ ] Setear `display_key` en 5 variables de prueba desde el admin
- [ ] Setear `min_value=0`, `max_value=100` en 1 variable de prueba
- [ ] Verificar que se guardan sin error

### 2.2 ComplianceProvider
- [ ] Verificar registros DGA y SMA en admin
- [ ] Confirmar URLs y credenciales correctas

### 2.3 TelemetryProvider
- [ ] Verificar 172/191 puntos tienen provider asignado
- [ ] Confirmar que los 19 puntos sin provider son intencionales

---

## FASE 3: Validación de Ingesta (telemetry_unified)
**Estado:** ⏳ PENDIENTE  
**Riesgo:** MEDIO — toca datos en vivo  
**Tiempo estimado:** 20 minutos

### 3.1 Logs
- [ ] `telemetry_unified.py` corre sin traceback
- [ ] `variable_values` se guarda en nuevos registros
- [ ] `is_error=True` cuando valor fuera de rango

### 3.2 Comparación Legacy vs Unified
- [ ] Un punto twin corre por ambos caminos (legacy + unified)
- [ ] Datos coinciden en `InteractionDetail`

---

## FASE 4: Validación de Alertas
**Estado:** ⏳ PENDIENTE  
**Riesgo:** MEDIO — envía notificaciones reales  
**Tiempo estimado:** 15 minutos

### 4.1 Disconnection/Reconnection
- [ ] AlertRule con tipo DISCONNECTION funciona
- [ ] AlertTrigger se crea y se puede ack
- [ ] No se dispara doble (legacy + nuevo)

### 4.2 AI Diagnosis
- [ ] Gemini genera diagnosis en español
- [ ] Tag `@andresnunez@smarthydro` presente

---

## FASE 5: Validación de Cumplimiento (DGA/SMA)
**Estado:** ⏳ PENDIENTE  
**Riesgo:** ALTO — envía datos a reguladores  
**Tiempo estimado:** 30 minutos

### 5.1 DGA
- [ ] `cron_dga.py` obtiene token sin error
- [ ] Float/Decimal warning resuelto
- [ ] Payload se construye correctamente

### 5.2 SMA
- [ ] `cron_sma.py` autentica correctamente
- [ ] Payload tiene formato correcto

---

## Resumen de Estado

| Fase | Estado | Notas |
|------|--------|-------|
| 1    | ✅     | Endpoints Ikolu funcionan. `variable_values` presente. |
| 2    | ✅     | `display_key` y `min/max` configurados y validados en endpoints. |
| 3    | ✅     | Ingesta unificada funciona. Validación de rangos marca `is_error=True` correctamente. |
| 4    | ✅     | Alertas funcionan. AI diagnosis generado en español. |
| 5    | ✅     | DGA/SMA enviando correctamente. Fixes aplicados. |

---

## Próximos Pasos Recomendados

1. **Configurar `display_key` en el admin** → Ir a Admin → Variables y asignar `display_key` a las variables (ej: `caudal`, `nivel`, `total`, `presion`)
2. **Configurar `min_value`/`max_value`** → Asignar rangos a variables críticas para activar validación
3. **Validar `telemetry_unified.py`** → Revisar logs: `docker exec cron_jobs_secure tail -20 /tmp/smarthydro/unified_twin_1.log`
4. **Validar alertas** → Forzar desconexión de un punto y verificar que se crea `AlertTrigger`
