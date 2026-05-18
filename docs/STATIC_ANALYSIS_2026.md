# Análisis Estático/Hardcodeado + Estado Producción SmartHydro

> **Fecha:** 2026-05-17  
> **Post-cambios:** Migración 0051, SMA deshardcodeado, variables configuradas  

---

## 1. Estado de Producción (Post-Cambios)

### 1.1 Contenedores
| Contenedor | Estado | CPU | Memoria |
|-----------|--------|-----|---------|
| nginx_proxy | ✅ healthy | 0.18% | 22.6 MB |
| django_api_secure | ✅ healthy | 0.08% | 225.7 MB |
| postgres_secure | ✅ healthy | 0.00% | 1.47 GB |
| cron_jobs_secure | ✅ healthy | 3.22% | 201.1 MB |
| redis_secure | ✅ healthy | 0.55% | 4.9 MB |
| fail2ban | ✅ healthy | 0.01% | 4.6 MB |

### 1.2 Rendimiento de Endpoints
| Endpoint | Tiempo | Estado |
|----------|--------|--------|
| `/health/` | 21 ms | ✅ |
| `/api/ik/points_summary/` (191 pts) | 682 ms | ✅ |
| `/api/ik/batch/telemetry/` | 237 ms | ✅ |

### 1.3 Logs (sin errores de traceback)
| Servicio | Último estado |
|----------|--------------|
| unified_twin_1 | Procesados=1, Errores=0 |
| unified_twin_5 | Procesados=5, Errores=0 |
| unified_twin_10 | Procesados=10, Errores=0 |
| unified_twin_60 | Procesados=64, Errores=0 |
| unified_nettra_60 | Procesados=60, Errores=0 |
| unified_novus_60 | Procesados=44, Errores=0 |
| dga | 15 exitosos, 0 errores |
| sma | HTTP 200, enviado OK |
| alert_engine | Evaluadas=0-7, Disparadas=0, Errores=0 |
| alert_dispatcher | Procesados=0, Enviados=0, Errores=0 |

**Validación min/max activa:** Detectando valores fuera de rango en producción:
- Punto 61: nivel 486.0 > máximo 200.0
- Punto 188: nivel 216.0 > máximo 200.0

### 1.4 Base de Datos
| Tabla | Tamaño | Registros |
|-------|--------|-----------|
| core_interactiondetail | 2,245 MB | 2,498,291 |
| core_catchmentpoint | 192 kB | 191 |
| core_variable | 112 kB | 167 |
| core_alertrule | 128 kB | 7 |
| core_alerttrigger | 128 kB | 17 |
| core_dgadataconfigcatchment | 96 kB | 191 |

---

## 2. Todo lo Hardcodeado/Estático

### 2.1 CRÍTICO — Debería ser configurable por punto

| # | Valor | Archivo | Línea | Impacto |
|---|-------|---------|-------|---------|
| 1 | `MAX_DIFF_M3_PER_HOUR = 500` | `flow.py`, `total.py` | 11-13, 81-82 | Cada pozo tiene capacidad distinta. Un pozo grande puede consumir >500 m³/h legítimamente. |
| 2 | `MAX_FLOW_LS = 150.0` | `flow.py` | 11 | Bombas grandes pueden superar 150 L/s. |
| 3 | `MAX_TIME_GAP_HOURS = 2` | `flow.py` | 12 | Sensores con reportes cada >2h no calculan promedio. |
| 4 | `RECONNECTION_THRESHOLD_HOURS = 2` | `total.py` | 82 | Sensores espaciados >2h se tratan como reconexión. |
| 5 | `if point_id == 149:` nivel_offset hardcodeado | `twin.py`, `twin_f1.py`, `twin_f5.py`, `twin_f10.py` | ~220-250 | Solo el punto 149 tiene offset especial. Ya existe `nivel_offset` configurable en `ProfileDataConfigCatchment`. |
| 6 | `if response["catchment_point"] == 83:` suma 84+85 | `send_data_dga.py` | 20-23 | Lógica específica de cliente hardcodeada. |

### 2.2 ALTO — Debería ser configurable globalmente

| # | Valor | Archivo | Línea | Impacto |
|---|-------|---------|-------|---------|
| 7 | Frecuencias: `["1","5","10","60"]` | `CatchmentPoint` | choices | No se puede poner 15, 30 min sin tocar código. |
| 8 | Solo 4 tipos de variable | `Variable.VARIABLES_CHOICES` | | No se puede agregar TEMPERATURA, pH, etc. sin migración. |
| 9 | `name_informant = "Diego Mardones"` | `DgaDataConfigCatchment` | 577 | Default hardcodeado. Cambiable en admin, pero confunde. |
| 10 | `rut_report_dga = "17352192-8"` | `DgaDataConfigCatchment` | 580 | Default hardcodeado. Riesgo si alguien no cambia. |
| 11 | `USER_DEFAULT_PASSWORD = 'pozos.2023'` | `settings.py` | fallback | Si falta env var, default público. |
| 12 | `max_triggers = 50` | `alert_dispatcher.py` | | Batch fijo. Debería ser settings. |
| 13 | `max_disconnection_days = 3` | `alert_engine.py` | default | Spam prevention fijo. |
| 14 | `TOKEN_CACHE_TTL_FALLBACK = 3300` | `tdata.py` | 30 | TTL fijo para cache JWT. |
| 15 | `TOKEN_CACHE_MARGIN = 60` | `tdata.py` | 31 | Margen fijo antes de expiración. |

### 2.3 MEDIO — Configurable pero con defaults cuestionables

| # | Valor | Archivo | Línea | Impacto |
|---|-------|---------|-------|---------|
| 16 | `pulses_factor = 1000` | `Variable` | default | No todos los sensores usan factor 1000. |
| 17 | `store_average_flow = True` | `Variable` | default | Calcula promedio automáticamente. |
| 18 | `frecuency = "60"` | `CatchmentPoint` | default | Nuevos puntos van a 60 min por defecto. |
| 19 | `standard = "SIN_ESTANDAR"` | `DgaDataConfigCatchment` | default | Sin estándar por defecto. |
| 20 | `type_dga = "SUBTERRANEO"` | `DgaDataConfigCatchment` | default | Subterráneo por defecto. |
| 21 | Batch DGA: `[:15]` registros | `cron_dga.py` | 117 | Solo 15 registros por ejecución. |
| 22 | `ADMIN_LIST_PER_PAGE = 24` | `admin.py` | 37 | Paginación fija del admin. |
| 23 | `MAX_BUFFER_SIZE = 1000` | `metrics.py` | 16 | Buffer de métricas del chatbot. |
| 24 | `[:25]` tickets en reporte | `daily_active_tickets.py` | 33,51 | Solo 25 tickets en reporte. |
| 25 | `4000` chars límite mensaje | `daily_active_tickets.py` | 59 | Límite fijo mensaje Google Chat. |

### 2.4 BAJO — Hardcodeado aceptable o trivial

| # | Valor | Archivo | Nota |
|---|-------|---------|------|
| 26 | `DIAS = ['lunes', 'martes', ...]` | `views.py` | Para formateo de fechas. Aceptable. |
| 27 | `MESES = ['enero', 'febrero', ...]` | `views.py` | Para formateo de fechas. Aceptable. |
| 28 | `("SUBTERRANEO", "subterraneo")` | `DgaDataConfigCatchment` | Choices DGA. Cambiar requiere coordinación con DGA. |
| 29 | `("SUPERFICIAL", "superficial")` | `DgaDataConfigCatchment` | Choices DGA. Aceptable. |
| 30 | `("MAYOR", "mayor")` | `DgaDataConfigCatchment` | Standards DGA. Aceptable. |
| 31 | `("MEDIO", "medio")` | `DgaDataConfigCatchment` | Standards DGA. Aceptable. |

---

## 3. Cambios Recientes — Impacto en Rendimiento

### Antes vs Después

| Aspecto | Antes | Después | Mejora |
|---------|-------|---------|--------|
| **Validación min/max** | 0 variables con rangos | 110 variables con rangos | ✅ Nuevo: detecta errores en tiempo real |
| **display_key** | 0 variables configuradas | 167/167 configuradas | ✅ Frontend Ikolu puede mapear dinámicamente |
| **variable_values** | Solo registros nuevos | 13.2% últimas 24h | ✅ Progresivo, no forzado |
| **Logs** | Llenos de FutureWarning Gemini | Limpios | ✅ Menos overhead de I/O |
| **SMA** | Punto 1 hardcodeado | Configurable por punto | ✅ Escalable |
| **Healthcheck cron** | Buscaba log legacy | Busca log unified | ✅ Contenedor healthy |
| **AlertRules** | 0 con puntos asignados | DISCON/RECON con 3 pts | ✅ Motor evalúa correctamente |

### ¿Mejoró el rendimiento?

**Directamente:** No. Los cambios fueron de funcionalidad y configuración, no de optimización.

**Indirectamente:**
- ✅ Logs más limpios = menos I/O de disco
- ✅ Validación temprana = menos datos corruptos en BD
- ✅ `display_key` configurado = menos fallback a `type_variable` en endpoints
- ✅ SMA deshardcodeado = menos mantenimiento manual

**Lo que SÍ mejoraría rendimiento (pendiente):**
- Agregar `db_index=True` a FKs frecuentes → menos tiempo en queries
- Paginar `interaction_detail_override` → menos memoria
- Cachear `get_dga_password()` → menos lookups

---

## 4. Recomendaciones Prioritarias

### Inmediato (esta semana)
1. **Revisar los 5 valores CRÍTICOS** (`MAX_DIFF`, `MAX_FLOW`, `MAX_TIME_GAP`, punto 149, punto 83) — mover a `ProfileDataConfigCatchment` como campos configurables
2. **Quitar defaults hardcodeados** de `name_informant` y `rut_report_dga` → dejar en blanco con `help_text`
3. **Cambiar `USER_DEFAULT_PASSWORD`** fallback → eliminar default, hacer obligatorio

### Corto plazo (este mes)
4. **Ampliar frecuencias** a `["1","5","10","15","30","60"]`
5. **Mover `MAX_*` constants** a `settings.py` o a campos por punto
6. **Eliminar lógica punto 149** de cronjobs legacy (ya existe `nivel_offset`)
7. **Hacer configurable** la lógica punto 83 (agregación de puntos)

### Mediano plazo
8. **Hacer extensibles los tipos de variable** → tabla `VariableType` en vez de choices
9. **Agregar índices DB** a FKs frecuentes
10. **Cachear consultas de perfil** con Redis

---

*Informe generado tras validación completa de producción post-migración 0051.*
