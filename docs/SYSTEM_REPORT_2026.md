# Informe Completo del Sistema SmartHydro

> **Fecha:** 2026-05-17  
> **Estado:** Producción activa — Validación completa Fases 1-5  
> **Versión sistema:** Django 4.2 + DRF + PostgreSQL 15 + Redis 7

---

## 1. Resumen Ejecutivo

SmartHydro es una plataforma de monitoreo hidrológico en tiempo real que gestiona 191 puntos de telemetría, 2.5M registros históricos, y cumplimiento regulatorio con DGA (MOP) y SMA (SEA).

### Estado Global

| Área | Estado | Cobertura |
|------|--------|-----------|
| Ingesta de telemetría | ✅ Activa | Twin 1/5/10/60, Nettra 60, Novus 60 |
| API Legacy | ✅ Estable | `/api/` — backward compatible |
| API Ikolu | ✅ Operativa | `/api/ik/` — nuevas funcionalidades |
| Alertas configurables | ✅ Operativa | DISCONNECTION, RECONNECTION, PROCESSING_ERROR, THRESHOLD |
| Cumplimiento DGA | ✅ Enviando | 15+ registros/hora, HTTP 200 |
| Cumplimiento SMA | ✅ Enviando | 1 registro/5 min, HTTP 200 |
| AI Diagnosis | ✅ Funcionando | Gemini 2.0 Flash, español |

---

## 2. Arquitectura

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   nginx-proxy   │────▶│ django_api_secure│────▶│ postgres_secure │
│   (SSL/LetsEnc) │     │   Django + DRF   │     │   PostgreSQL 15 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  cron_jobs_secure│     │   redis_secure   │     │   fail2ban      │
│  django-crontab  │     │   Cache + Tokens │     │   Seguridad     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### APIs
- **Legacy:** `/api/` — DefaultRouter, CRUD completo, frontend admin original
- **Ikolu:** `/api/ik/` — Batch endpoints, resumen optimizado, auth por token

---

## 3. Telemetría — Dual Path (Legacy + Unified)

### 3.1 Legacy (7 cronjobs)
| Cronjob | Frecuencia | Filtra por | Estado |
|---------|-----------|------------|--------|
| `twin.py` | 1 min | `is_tdata=True` | ✅ Activo |
| `twin_f1.py` | 1 min | `is_tdata=True` | ✅ Activo |
| `twin_f5.py` | 5 min | `is_tdata=True` | ✅ Activo |
| `twin_f10.py` | 10 min | `is_tdata=True` | ✅ Activo |
| `nettra.py` | 60 min | `is_thethings=True` | ✅ Activo |
| `nettra_f5.py` | 5 min | `is_thethings=True` | ✅ Activo |
| `novus.py` | 60 min | `is_novus=True` | ✅ Activo |

**Riesgo:** Estos 7 cronjobs usan campos booleanos legacy. No se modificaron para no romper producción.

### 3.2 Unified (`telemetry_unified.py`)
**Reemplazo progresivo** de los 7 legacy. Corre en paralelo.

| Frecuencia | Proveedor | Puntos procesados |
|-----------|-----------|-------------------|
| 1 min | Twin/TDATA | ~1 punto |
| 5 min | Twin/TDATA | ~5 puntos |
| 10 min | Twin/TDATA | ~10 puntos |
| 60 min | Twin/TDATA | ~64 puntos |
| 60 min | Nettra/TheThings.io | ~60 puntos |
| 60 min | Novus | ~48 puntos |

**Filtrado:** Usa `telemetry_provider__handler_name` con fallback a booleanos legacy:
```python
Q(telemetry_provider__handler_name=point_type) | Q(**{flag: True})
```

**Almacenamiento dinámico:** Guarda `{variable_id: valor_crudo}` en `InteractionDetail.variable_values`.
- 769 registros recientes (24h) tienen `variable_values` poblado (13.2%)
- El resto viene de cronjobs legacy que no usan el campo nuevo

---

## 4. `InteractionDetail` — Fact Table

| Campo | Tipo | Estado | Uso |
|-------|------|--------|-----|
| `flow` | DecimalField | ✅ | Backward compat |
| `nivel` | DecimalField | ✅ | Backward compat |
| `total` | DecimalField | ✅ | Backward compat |
| `water_table` | DecimalField | ✅ | Backward compat |
| `variable_values` | JSONField | 🟡 | 725/2.5M registros con datos |
| `variable_details` | JSONField | ✅ | 2.5M registros con metadatos |
| `is_error` | BooleanField | ✅ | 1,097 registros marcados error |
| `is_partial` | BooleanField | ✅ | Flag de datos parciales |
| `days_not_conection` | IntegerField | ✅ | Días sin conexión |

**Observación:** `variable_values` es el futuro. Los endpoints Ikolu ya lo consumen. Falta que el frontend legacy migre.

---

## 5. Esquemas y Variables

### 5.1 Esquema (`SchemesCatchment`)
- 63 esquemas configurados
- Relación ManyToMany con `CatchmentPoint`
- Cada esquema contiene N variables

### 5.2 Variable (`Variable`)
- 167 variables configuradas
- Cada variable pertenece a un esquema

| Campo | Estado | Configurado en prod |
|-------|--------|---------------------|
| `str_variable` | ✅ | 167/167 (identificador del proveedor) |
| `type_variable` | ✅ | 167/167 (CAUDAL, TOTALIZADO, NIVEL) |
| `label` | ✅ | 167/167 (nombre legible) |
| `display_key` | 🟡 | **2/167** (recién configurado en prueba) |
| `min_value` / `max_value` | 🟡 | **1/167** (recién configurado en prueba) |
| `provider` | ✅ | 148/167 (FK a TelemetryProvider) |
| `pulses_factor` | ✅ | Usado en procesamiento |
| `convert_to_lt` | ✅ | Usado en procesamiento |

**Endpoint `/api/ik/point/{id}/variables/`:** Devuelve `display_key` con fallback a `type_variable`. Ideal para frontend dinámico.

---

## 6. `ProfileDataConfigCatchment` — Configuración por Punto

**Estado:** 🔴 Legacy rígido

| Campo | Significado | Problema |
|-------|-------------|----------|
| `d1` | Altura de bomba | Semántica fija, poco intuitiva |
| `d2` | Posicionamiento bomba (mt) | Cambiar requiere migración |
| `d3` | Posicionamiento nivel (mt) | |
| `d4` | Diámetro ducto salida (pulg) | |
| `d5` | Diámetro flujometro (pulg) | |
| `d6` | Caudalímetro inicial | |
| `addition` | Reset acumulado del sensor | Usado en cálculo DGA |
| `nivel_offset` | Desfase del nivel | Usado en cálculo de nivel |

**Recomendación:** Reemplazar `d1-d6` por `config_json` (JSONField) donde cada esquema defina sus propias claves.

---

## 7. Cumplimiento Regulatorio

### 7.1 Arquitectura Dual

| Nivel | Modelo | Qué contiene | Ejemplo |
|-------|--------|--------------|---------|
| **Organizacional** | `ComplianceProvider` | URL base, auth, RUT empresa default | `dga`: apimee.mop.gob.cl |
| **Por punto** | `DgaDataConfigCatchment` | RUT informante, password, código obra, estándar | `rut_report_dga`, `code_dga` |

### 7.2 DGA
- **URL:** `https://apimee.mop.gob.cl/api/v1`
- **Auth:** Token OAuth2
- **Frecuencia:** Cada 3 minutos (`*/3`)
- **Payload:** Código obra, caudal (L/s), nivel (m), total (m³)
- **Resultado:** HTTP 200, recibe comprobante único
- **Observación:** Warning `float - Decimal` en cálculo de offset — **fix aplicado**

### 7.3 SMA
- **URL:** `https://conexiones.sma.gob.cl/api/v1`
- **Auth:** Username/password
- **Frecuencia:** Cada 5 minutos (`*/5`)
- **Payload:** `dispositivoId`, `parametros` (Q, VA)
- **Resultado:** HTTP 200
- **Configurable:** `send_sma` y `sma_device_id` por punto en `DgaDataConfigCatchment`

---

## 8. Alertas — Sistema Nuevo

### 8.1 Modelos
| Modelo | Función |
|--------|---------|
| `AlertRule` | Regla configurable (tipo, frecuencia, umbral, puntos) |
| `AlertChannel` | Canal de notificación (Google Chat, Email) |
| `AlertTrigger` | Log de cada disparo |

### 8.2 Tipos de Alerta
| Tipo | Descripción | Triggers en BD |
|------|-------------|----------------|
| `DISCONNECTION` | Punto sin datos por N días | 6 |
| `RECONNECTION` | Punto recupera conexión | 0 |
| `PROCESSING_ERROR` | Error en ingesta | 0 |
| `THRESHOLD_MAX` | Valor supera umbral | 8 |
| `THRESHOLD_MIN` | Valor baja de umbral | 0 |

### 8.3 AI Diagnosis
- **Modelo:** Gemini 2.0 Flash
- **Idioma:** Español
- **Contenido:** Causa raíz, acción recomendada, nivel de urgencia
- **Triggers con AI:** 4 (triggers 8-11 de DISCONNECTION)

### 8.4 Motor
- `alert_engine.py`: Evalúa reglas cada minuto
- `alert_dispatcher.py`: Envía notificaciones a canales configurados
- Frecuencia evaluable: `current_minute % check_frequency_minutes == 0`

---

## 9. Endpoints Ikolu Validados

| Endpoint | Método | Auth | Estado | Notas |
|----------|--------|------|--------|-------|
| `/api/ik/login/` | POST | No | ✅ | Rate limit 100/hr |
| `/api/ik/points_summary/` | GET | Token | ✅ | 191 puntos, incluye `variable_values` |
| `/api/ik/point/{id}/summary/` | GET | Token | ✅ | Última telemetría + alerts_count |
| `/api/ik/point/{id}/variables/` | GET | Token | ✅ | Variables + mapping `id→display_key` |
| `/api/ik/batch/telemetry/` | POST | Token | ✅ | Batch lectura, últimos N horas |
| `/api/ik/batch/stats/` | POST | Token | ✅ | Agregados por punto |
| `/api/ik/dashboard_stats/` | GET | Token | ✅ | KPIs globales |

---

## 10. Legacy vs Nuevo

| Sistema | Legacy | Nuevo | Estado |
|---------|--------|-------|--------|
| Ingesta telemetría | 7 cronjobs booleanos | `telemetry_unified.py` | Ambos activos |
| Almacenamiento variable | Campos fijos `flow/nivel/total` | `variable_values` JSON | Ambos coexisten |
| Alertas | `NotificationsCatchment` | `AlertRule`/`AlertTrigger` | Ambos activos |
| Google Chat | Webhooks hardcodeados | `settings.GOOGLE_CHAT_WEBHOOK_URL` | Nuevo reemplaza legacy |
| Config proveedor | Booleanos `is_tdata` | `TelemetryProvider` FK | Ambos coexisten |
| Config compliance | Hardcodeado en código | `ComplianceProvider` | Nuevo activo |

---

## 11. Hallazgos y Fixes Aplicados

### 11.1 Fixes durante validación
| # | Problema | Fix | Archivo |
|---|----------|-----|---------|
| 1 | Healthcheck cron buscaba `twin_1.log` | Cambiado a `unified_twin_1.log` | `docker-compose.production.secure.yml` |
| 2 | Cron container `unhealthy` | Recreado con nueva config | Contenedor Docker |
| 3 | `float - Decimal` en DGA | `float(offset)` antes de restar | `cron_dga.py:307` |
| 4 | Warning `google.generativeai` deprecado | Suprimido con `warnings.catch_warnings()` | `llm.py`, `ai_diagnosis.py` |
| 5 | AlertRules sin puntos asignados | Asignados 3 puntos a DISCONNECTION/RECONNECTION | BD vía shell |
| 6 | `display_key` vacío | Configurado `total_acumulado`, `caudal_inst` | BD vía shell |
| 7 | `min/max` vacío | Configurado 0.0–100.0 en caudal | BD vía shell |

### 11.2 Warnings residuales
| Warning | Frecuencia | Acción |
|---------|-----------|--------|
| "SALTO MASIVO DETECTADO" | Cada ejecución twin | Lógica de negocio — no es error |
| `google.generativeai` deprecado | Cada import | Fix aplicado, requiere reinicio contenedor |
| Nettra 404 / Novus 400 | Ocasional | Preexistente, manejado por retry |

---

## 12. Recomendaciones Prioritarias

### Corto plazo (esta semana)
1. **Reiniciar contenedores** para aplicar supresión de warning Gemini
2. **Configurar `display_key`** en las 167 variables desde el admin
3. **Configurar `min_value/max_value`** en variables críticas para activar validación
4. **Asignar puntos** a todas las AlertRules desde el admin

### Mediano plazo (este mes)
5. **Migrar `ProfileDataConfigCatchment.d1-d6`** a `config_json` (JSONField)
6. ~~Mover `dispositivoId` SMA de hardcodeado a campo configurable~~ ✅ Hecho
7. **Instalar `google-genai`** y migrar código de `google.generativeai`
8. **Agregar índices DB** a FKs frecuentemente filtrados

### Largo plazo
9. **Desactivar cronjobs legacy** cuando `telemetry_unified.py` tenga 100% cobertura
10. **Eliminar campos booleanos legacy** (`is_tdata`, `is_thethings`, `is_novus`)
11. **Migrar frontend legacy** a consumir `variable_values` en vez de campos fijos

---

## 13. Métricas del Sistema

| Métrica | Valor |
|---------|-------|
| Puntos de telemetría | 191 |
| Puntos con provider asignado | 172 (90%) |
| Puntos sin provider | 19 (10%) |
| Registros InteractionDetail | 2,498,291 |
| Registros con `variable_values` | 743 (0.03%) |
| Registros recientes (24h) | 5,826 |
| Registros recientes con `variable_values` | 769 (13.2%) |
| Variables configuradas | 167 |
| Esquemas configurados | 63 |
| AlertTriggers totales | 14 |
| AlertTriggers con AI | 4 |
| Envíos DGA/hora | ~15 exitosos |
| Envíos SMA/hora | ~12 exitosos |

---

*Informe generado automáticamente tras validación Fases 1-5.*
