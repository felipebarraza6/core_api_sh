# Resumen de Limpieza y Automatización — 2026-05-17

## Commits realizados

1. `ad45d73` — BACKUP PRE-LIMPIEZA (estado anterior consolidado)
2. `7884d1e` — HARDODES AUTOMATIZADOS (MAX_DIFF, MAX_FLOW, punto 83)
3. `93e804d` — LIMPIEZA: Eliminar 8 archivos cronjobs legacy

---

## 1. Hardcodes Automatizados

### Antes → Después

| Hardcode | Antes | Ahora | Archivo modificado |
|----------|-------|-------|-------------------|
| MAX_DIFF_M3_PER_HOUR = 500 | Constante global en `flow.py` + `total.py` | `ProfileDataConfigCatchment.max_diff_m3_per_hour` (default 500) | `flow.py`, `total.py`, modelo |
| MAX_FLOW_LS = 150 | Constante global en `flow.py` | `ProfileDataConfigCatchment.max_flow_ls` (default 150) | `flow.py`, modelo |
| Punto 83 suma 84+85 | `if point_id == 83:` hardcodeado en `send_data_dga.py` | `DgaDataConfigCatchment.dga_aggregate_points = [84, 85]` | `send_data_dga.py`, `cron_dga.py`, modelo |

### Configuración aplicada en producción

```python
# Punto 83 (mantiene comportamiento anterior)
DgaDataConfigCatchment.objects.filter(point_catchment_id=83).update(
    dga_aggregate_points=[84, 85]
)
```

---

## 2. Código Legacy Eliminado

### Archivos borrados (8 total)

| Archivo | Líneas | Estado antes de borrar |
|---------|--------|------------------------|
| `api/cronjobs/telemetry/twin.py` | ~350 | No ejecutado (log vacío) |
| `api/cronjobs/telemetry/twin_f1.py` | ~350 | No ejecutado |
| `api/cronjobs/telemetry/twin_f5.py` | ~350 | No ejecutado |
| `api/cronjobs/telemetry/twin_f10.py` | ~350 | No ejecutado |
| `api/cronjobs/telemetry/nettra.py` | ~300 | No ejecutado |
| `api/cronjobs/telemetry/nettra_f5.py` | ~300 | No ejecutado |
| `api/cronjobs/telemetry/novus.py` | ~250 | No ejecutado |
| `api/cronjobs/telemetry/controllers/total_backup.py` | ~100 | No importado |

**Total eliminado:** ~3,037 líneas de código

### Por qué era seguro borrarlos

1. **Crontab solo tenía unified:** `docker exec cron_jobs_secure crontab -l` mostraba solo `unified_twin_1.log`, `unified_twin_5.log`, etc.
2. **Logs legacy vacíos:** `twin_1.log` tenía 0 bytes
3. **Nadie los importaba:** `grep -rn "from.*twin import"` no encontró imports activos
4. **Settings tenían comentarios:** Los cronjobs legacy estaban comentados en `settings.py`
5. **Unified ya los reemplazaba:** `telemetry_unified.py` procesa Twin 1/5/10/60, Nettra 60, Novus 60

---

## 3. Qué está en Función vs Qué quedó Fuera

### ✅ EN FUNCIÓN (activo en producción)

#### Ingesta
| Componente | Archivo | Estado |
|-----------|---------|--------|
| Runner unificado | `telemetry_unified.py` | ✅ Activo (TWIN 1/5/10/60, Nettra 60, Novus 60) |
| Procesamiento | `unified_processing.py` | ✅ Activo |
| Totalizados | `total.py` | ✅ Activo |
| Caudal | `flow.py` | ✅ Activo |
| Nivel | `nivel.py` | ✅ Activo |
| Getter universal | `getters/universal.py` | ✅ Activo |
| Getter TDATA | `getters/tdata.py` | ✅ Activo |
| Getter TheThings | `getters/thingsio.py` | ✅ Activo |
| Getter genérico | `getters/generic.py` | ✅ Activo |

#### Cumplimiento
| Componente | Archivo | Estado |
|-----------|---------|--------|
| DGA sender | `send_data_dga.py` | ✅ Activo |
| DGA cron | `cron_dga.py` | ✅ Activo (cada 3 min) |
| SMA cron | `cron_sma.py` | ✅ Activo (cada 5 min) |
| Cálculos caudal | `caudal_calculations.py` | ✅ Activo |

#### Alertas
| Componente | Archivo | Estado |
|-----------|---------|--------|
| Motor | `alert_engine.py` | ✅ Activo (cada minuto) |
| Dispatcher | `alert_dispatcher.py` | ✅ Activo (cada minuto) |
| AI diagnosis | `ai_diagnosis.py` | ✅ Activo (Gemini) |
| Evaluador legacy | `alert_evaluator.py` | 🟡 Existe pero no usado |
| Cron alerts | `cron_alerts.py` | 🟡 Existe pero deprecado |

#### API
| Componente | Ruta | Estado |
|-----------|------|--------|
| Legacy | `/api/` | ✅ Activo (no tocar) |
| Ikolu | `/api/ik/` | ✅ Activo (mejoras) |

#### Modelos principales
| Modelo | Estado |
|--------|--------|
| `CatchmentPoint` | ✅ |
| `InteractionDetail` | ✅ |
| `Variable` | ✅ (con display_key, min/max) |
| `SchemesCatchment` | ✅ |
| `ProfileDataConfigCatchment` | ✅ (con max_diff, max_flow nuevos) |
| `DgaDataConfigCatchment` | ✅ (con send_sma, sma_device_id, dga_aggregate_points nuevos) |
| `TelemetryProvider` | ✅ |
| `ComplianceProvider` | ✅ |
| `AlertRule` | ✅ |
| `AlertTrigger` | ✅ |

### ❌ FUERA DE FUNCIÓN (eliminado)

| Componente | Razón |
|-----------|-------|
| `twin.py` | Reemplazado por `telemetry_unified.py` |
| `twin_f1.py` | Reemplazado por `telemetry_unified.py` |
| `twin_f5.py` | Reemplazado por `telemetry_unified.py` |
| `twin_f10.py` | Reemplazado por `telemetry_unified.py` |
| `nettra.py` | Reemplazado por `telemetry_unified.py` |
| `nettra_f5.py` | Reemplazado por `telemetry_unified.py` |
| `novus.py` | Reemplazado por `telemetry_unified.py` |
| `total_backup.py` | No usado |

### 🟡 PENDIENTE (existe pero no se usa activamente)

| Componente | Nota |
|-----------|------|
| `alert_evaluator.py` | Legacy, reemplazado por `alert_engine.py` |
| `cron_alerts.py` | Legacy, reemplazado por alert engine + dispatcher |
| `google_chat.py` (funciones legacy) | `check_and_notify_*` tienen early return `[MIGRADO]` |
| `NotificationsCatchment` | Modelo legacy, reemplazado por `AlertTrigger` |

---

## 4. Estado de Endpoints

### Legacy (`/api/`) — INTACTOS
| Endpoint | Estado |
|----------|--------|
| `/api/catchment_point/` | ✅ 200, 191 puntos |
| `/api/interaction_detail/` | ✅ 200, 2.5M registros |
| `/api/dga_data_config_catchment/` | ✅ 200, incluye nuevos campos |
| `/api/management/` | ✅ 200 (requiere staff) |

### Ikolu (`/api/ik/`) — OPERATIVOS
| Endpoint | Estado |
|----------|--------|
| `/api/ik/points_summary/` | ✅ |
| `/api/ik/point/{id}/summary/` | ✅ |
| `/api/ik/point/{id}/variables/` | ✅ |
| `/api/ik/batch/telemetry/` | ✅ |
| `/api/ik/batch/stats/` | ✅ |

---

## 5. Métricas Post-Limpieza

| Métrica | Valor |
|---------|-------|
| Líneas de código eliminadas | ~3,037 |
| Archivos eliminados | 8 |
| Hardcodes automatizados | 3 |
| Migraciones aplicadas | 2 (0051, 0052) |
| Contenedores healthy | 6/6 |
| Registros en BD | 2,498,291 |

---

*Para revertir: `git revert 93e804d` (limpieza) y `git revert 7884d1e` (hardcodes)*
