# Plan de Validación y Corrección de Telemetría — SmartHydro

> **Generado:** 2026-05-22  
> **Estado:** Post-crisis Redis + fixes aplicados  
> **Puntos auditados:** 191

---

## 1. Hallazgos de Auditoría Global

### 1.1 Distribución de puntos

| Provider | Total | Sin TOTALIZADO | Sensor nunca funcionó | Con datos válidos |
|----------|-------|----------------|----------------------|-------------------|
| TWIN     | 64    | 4 (NIVEL solo) | 6                    | 54                |
| NOVUS    | 48    | 0              | 2                    | 46                |
| NETTRA   | 60    | 0              | 12                   | 48                |
| OTHER    | 19    | 16             | 1                    | 2                 |
| **Total**| **191** | **20**       | **21**               | **150**           |

### 1.2 Clasificación de severidad (últimos 90 días)

| Severidad | Cantidad | Descripción |
|-----------|----------|-------------|
| 🔴 CRITICAL | 18 | Sensor nunca funcionó + tiene TOTALIZADO. Requieren revisión física o reconfiguración. |
| 🟠 HIGH | 114 | Gaps > 3h, saltos > 500 m³/h, totales NULL, o monotonicidad rota. |
| 🟡 MEDIUM | 25 | Gaps menores (3-7h), normal en algunos providers. |
| 🔵 INFO | 29 | Sin variable TOTALIZADO (NIVEL/CAUDAL solo). Esperado. |
| 🟢 OK | 5 | Sin problemas detectados. |

### 1.3 Problemas específicos identificados

#### A. Sensores que nunca funcionaron (21 puntos)
Estos puntos tienen variable TOTALIZADO configurada pero **nunca** han reportado `pulses > 0`. Todos sus registros tienen `pulses=0`.

| ID | Nombre | Provider | Registros |
|----|--------|----------|-----------|
| 9 | P2 | TWIN | 3,495 |
| 33 | Coronel - Sondaje 6056 | NETTRA | — |
| 35 | Rancagua Machali - Sondaje 1547 | NETTRA | — |
| 39 | San Vicente de Tagua Tagua - Sondaje 6607 | NETTRA | — |
| 40 | Codegua La Punta - Sondaje 6038 | NETTRA | — |
| 44 | San Vicente de Tagua Tagua - Sondaje 830 | NETTRA | — |
| 46 | Lo Miranda - Sondaje 703 | NETTRA | — |
| 49 | Lota - Quebrada Mayor | NETTRA | — |
| 50 | Lota - Estero Luma | NETTRA | — |
| 51 | Lota - Colcura Alto | NETTRA | — |
| 76 | P 3 | NOVUS | — |
| 133 | Pablo Neruda 3 | NOVUS | — |
| 147 | P4 | TWIN | 251 |
| 158 | San Jose 2 | TWIN | 6,940 |
| 178 | Pivote 3 | TWIN | 4,807 |
| 192 | Romana | TWIN | 3,721 |
| 193 | Estacionamiento | TWIN | 3,554 |
| 198 | Test Point All | OTHER | — |

**Acción:** Revisión física del sensor o reconfiguración de variables. Si no miden volumen, eliminar variable TOTALIZADO.

#### B. Totales NULL en puntos con historial (9 puntos)
Puntos que SÍ tienen datos válidos pero también registros con `total=NULL`.

| ID | Nombre | Provider | NULLs | Acción |
|----|--------|----------|-------|--------|
| 61 | Planta 1 P1 | TWIN | 347 | Corregir vía script de propagación |
| 62 | Planta 2 P1 | TWIN | 344 | Corregir vía script de propagación |
| 63 | Complejo Industrial P1 | TWIN | 544 | Corregir vía script de propagación |
| 64 | Campo Deportivo | TWIN | 3 | Corregir vía script de propagación |
| 146 | PF Renca | TWIN | 342 | Corregir vía script de propagación |
| 156 | Selva Negra | TWIN | 1 | Corregir vía script de propagación |
| 162 | Caseta de Riego | TWIN | 15 | Corregir vía script de propagación |
| 172 | Freire | TWIN | 1 | Corregir vía script de propagación |
| 38 | Rancagua Machali - Sondaje 232 | NETTRA | 4,913 | **Este punto solo mide NIVEL** — no debería tener TOTALIZADO. Los NULLs son normales. Revisar config. |

#### C. Saltos anómalos (> 500 m³ en 1h)

| ID | Nombre | Max salto | Notas |
|----|--------|-----------|-------|
| 102 | Pozo | 6,524,497 | Reset desde 0 — probable bug histórico |
| 141 | Pesqueras 4 | 2,384,920 | Reset desde 0 |
| 47 | Pichilemu - Dren Nilahue | 1,553,290 | Reset desde 0 |
| 14 | P100 | 1,437,240 | Reset desde 0 |
| 3 | San Vicente de Tagua Tagua | 1,399,750 | Reset desde 0 |
| 135 | Romeral P6013 | 1,152,468 | Reset parcial |
| 177 | Trilico Corrales | 948,404 | Reset parcial |
| 12 | Cerrillos | 238,979 | Reset parcial |

**Patrón común:** Muchos saltos ocurren cuando el `total` anterior era `0` (por bug del anti-salto que ya fue corregido) y luego el sensor reportó su valor real. Estos **no son errores actuales** — son recuperaciones legítimas de puntos que estuvieron congelados en 0.

#### D. Monotonicidad rota (total decrece)

| ID | Nombre | Decrementos | Notas |
|----|--------|-------------|-------|
| 77 | P 2 | 13 | NOVUS — probable reset falso detectado |
| 141 | Pesqueras 4 | 1 | Salto masivo |
| 110 | P3 | 4 | NOVUS — sensor desconectado? |
| 146 | PF Renca | 4 | TWIN — gaps |

---

## 2. Plan de Corrección por Fases

### FASE 0 — Preparación (1 día)

**Objetivo:** Tener herramientas y backups listos antes de tocar datos.

- [x] Script de auditoría (`scripts/audit_telemetry_health.py`) — ✅ Listo
- [ ] Backup completo de BD antes de cualquier corrección masiva
- [ ] Script de corrección de monotonicidad (`scripts/fix_total_monotonicity.py`) — extender para TWIN
- [ ] Script de backfill automático para gaps identificados

### FASE 1 — Clasificación y Limpieza (2-3 días)

**Objetivo:** Separar puntos que requieren acción física vs. los que solo necesitan corrección de datos.

1. **Revisar 21 puntos CRITICAL** (sensor nunca funcionó):
   - Contactar cliente/operador para verificar estado físico del sensor.
   - Si el sensor está dañado/desconectado: marcar punto como `is_active=False` o crear alerta.
   - Si el punto no debe medir volumen (solo NIVEL): eliminar variable TOTALIZADO.
   - Si el punto es nuevo y aún no tiene datos: documentar fecha esperada de activación.

2. **Revisar punto 38 (NETTRA con 4,913 NULLs)**:
   - Confirmar si debe tener TOTALIZADO o no.
   - Si no: eliminar variable TOTALIZADO → NULLs desaparecerán del scope.

3. **Puntos INFO (29 sin TOTALIZADO)**:
   - Validar que efectivamente no necesitan medir volumen.
   - Documentar excepciones.

### FASE 2 — Corrección de Datos Históricos (3-5 días)

**Objetivo:** Limpiar registros con `total=NULL` y corregir monotonicidad rota.

#### 2.1 Propagar totales NULL (9 puntos)

Usar script unificado que:
1. Para cada punto, ordene registros cronológicamente.
2. Encuentre el último `total` válido antes de un gap de NULLs.
3. Propague ese `total` a todos los registros NULL consecutivos.
4. Establezca `total_diff=0` en registros propagados.
5. Para TWIN: si `pulses=0` en el registro propagado, es correcto (sin consumo).
6. Para TWIN: si `pulses>0` en el registro propagado, calcular `total` normalmente.

**Estimación:** ~1,500 registros a corregir. Script automatizado: 30 min.

#### 2.2 Corregir saltos desde 0 (puntos congelados por bug anti-salto)

Algunos puntos tuvieron `total=0` por el bug del anti-salto (ya corregido). Cuando el sensor volvió a reportar, el total saltó desde 0 a su valor real.

**No requieren corrección** — el salto es una **recuperación legítima**. El total actual es correcto.

**Pero** los `total_diff` de esas horas muestran consumo masivo, lo cual distorsiona reportes.

Acción:
- Para registros donde `total` saltó desde `0` a `> 1000` sin desconexión previa documentada:
  - Establecer `total_diff=0` para esa hora.
  - Establecer `total_today_diff` recalculado desde el inicio del día.
  - Documentar en log de auditoría.

#### 2.3 Corregir monotonicidad rota (DECREMENT)

Para puntos con totales decrecientes:
- Investigar si fue un reset real del contador físico.
- Si fue reset real: el `addition` del perfil ya debería haberse ajustado automáticamente.
- Si fue error (sensor desconectado devolviendo 0, ya corregido en código): propagar último total válido.

### FASE 3 — Backfill de Gaps (5-7 días)

**Objetivo:** Recuperar datos faltantes de las APIs de providers.

#### 3.1 Gaps identificados

Los gaps de 49h-69h son típicamente de la crisis Redis (19-21 mayo). Otros gaps pueden ser:
- Mantenimiento programado
- Fallas de red
- Cambio de configuración

#### 3.2 Backfill por provider

| Provider | Backfill posible | Estrategia |
|----------|-----------------|------------|
| TWIN | ✅ Sí (histórico hasta 30-90 días) | Script `backfill_point_range.py` ya funciona |
| NOVUS | ✅ Sí (histórico TagolO) | Script `backfill_point_range.py` ya funciona |
| NETTRA | ❌ No (solo último valor) | No se puede backfill. Replicar último registro válido si aplica. |

**Acción:**
1. Para cada punto con gap > 24h en los últimos 30 días:
   - Si es TWIN/NOVUS: ejecutar backfill del rango.
   - Si es NETTRA: no hay nada que hacer (API no soporta histórico).
   - Establecer `is_error=True` en buckets sin datos para distinguir de `pulses=0`.

2. Post-backfill: ejecutar recálculo de totales en cascada.

**Estimación:** ~60 puntos con gaps > 24h. Proceso automatizado: 2-4 horas.

### FASE 4 — Validación Continua (implementación inmediata)

**Objetivo:** Detectar problemas antes de que se acumulen.

#### 4.1 Script de validación diaria

Crear cronjob diario (`scripts/validate_telemetry_daily.py`) que:
1. Ejecute `audit_telemetry_health.py --days 1`.
2. Genere alerta si:
   - Un punto tiene > 3 registros con `total=NULL` en 24h.
   - Un punto tiene un salto > `max_diff_m3_per_hour` configurado.
   - Un punto tiene monotonicidad rota (total decrece).
   - Un punto tiene gap > 2x su frecuencia configurada.
3. Envíe resumen a Google Chat / email.

#### 4.2 Dashboard de salud

Endpoint API nuevo: `GET /api/ik/telemetry/health/`
- Retorna JSON con estado de todos los puntos.
- Filtrable por `provider`, `severity`, `project`.
- Útil para monitoreo en tiempo real.

#### 4.3 Alertas proactivas

Modificar `telemetry_unified.py` para que:
- Cuando un punto tiene `days_not_conection > 0`, cree una notificación tipo `WARNING`.
- Cuando un punto tiene `pulses=0` por > 3 horas consecutivas (y tiene TOTALIZADO), marque `is_error=True` explícitamente.

---

## 3. Scripts y Herramientas Requeridos

| Script | Estado | Descripción |
|--------|--------|-------------|
| `audit_telemetry_health.py` | ✅ Listo | Auditoría global de salud |
| `fix_total_monotonicity.py` | 🔄 Pendiente | Extender script actual para TWIN + propagación en cascada |
| `backfill_gaps_batch.py` | 🔄 Pendiente | Backfill automático de todos los gaps > 24h detectados |
| `validate_telemetry_daily.py` | 🔄 Pendiente | Validación diaria + alertas |
| `views_telemetry_health.py` | 🔄 Pendiente | Endpoint API de salud |

---

## 4. Cambios en Código (ya aplicados + pendientes)

### ✅ Ya aplicados (2026-05-22)

1. `total.py`: `pulses=0` → nunca detecta reset, siempre mantiene `last_total`.
2. `backfill_point_range.py`: `recalc_totals_for_range()` propaga último total válido cuando `pulses=0`.
3. Fix datos: 134 registros en 6 puntos corregidos.
4. Fix Redis auth + `requirepass`.

### 🔄 Pendientes

1. **Distinguir `pulses=0` real vs. error:** En TWIN, `pulses=0` puede ser "sin consumo" (legítimo) o "sensor no respondió" (error). La distinción debería basarse en si el getter devolvió `date_time=None`.
   - Si `date_time=None` + `value=0` → `is_error=True` (ya implementado parcialmente).
   - Si `date_time=válido` + `value=0` → para TWIN es sin consumo; para NOVUS es desconexión.

2. **NETTRA sin histórico:** Implementar replicación del último registro válido cuando el getter falla, para no dejar gaps.

3. **Anti-salto refinado:** El límite actual es 500 m³/h por defecto. Algunos puntos legítimamente consumen más. Revisar `max_diff_m3_per_hour` por punto.

---

## 5. Cronograma Estimado

| Fase | Duración | Bloqueante |
|------|----------|------------|
| FASE 0 — Preparación | 1 día | — |
| FASE 1 — Clasificación | 2-3 días | Requiere contacto con operadores/clientes |
| FASE 2 — Corrección datos | 3-5 días | Depende de FASE 1 |
| FASE 3 — Backfill gaps | 5-7 días | Depende de FASE 2. APIs TWIN/NOVUS pueden tener límites. |
| FASE 4 — Validación continua | 2-3 días | Puede hacerse en paralelo con FASE 3 |
| **Total** | **13-19 días** | |

---

## 6. Métricas de Éxito

Al finalizar el plan, se espera:

- [ ] ≥ 95% de puntos activos en estado `OK` o `INFO`.
- [ ] 0 puntos con `total=NULL` en los últimos 30 días.
- [ ] 0 saltos anómalos no documentados en 30 días.
- [ ] 100% de gaps > 24h explicados (backfill completado o documentado como irreparable).
- [ ] Dashboard de salud accesible vía API.
- [ ] Alerta automática en < 4h cuando un punto deja de reportar.

---

## 7. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Backfill TWIN excede límite de API | Media | Alto | Paginación + throttling + monitoreo de rate limits |
| Corrección masiva rompe totales existentes | Baja | Alto | Backup previo + validación post-corrección |
| Cliente no responde sobre sensores dañados | Alta | Medio | Marcar como `needs_maintenance` y seguir con los demás |
| NETTRA sigue sin histórico | Alta | Medio | Implementar replicación como solución temporal |
| APIs de providers cambian | Baja | Medio | Tests de integración + monitoreo de errores |

---

## 8. Próximos pasos inmediatos

1. **Tu decisión:** ¿Aprobamos el plan? ¿Empezamos con FASE 0 + FASE 1?
2. **Prioridad:** ¿Quieres que priorice algún proyecto/cliente específico?
3. **Sensores CRITICAL:** ¿Tienes contacto con los operadores de los 21 puntos con sensor dañado?
