# 🔬 Análisis Completo del Sistema SmartHydro
**Fecha:** 2026-04-30  
**Alcance:** Cronjobs, Seguridad/Auth, Modelos/DB, Admin/UI  
**Instrucción:** Solo análisis, sin modificaciones.

---

## 🎯 RESUMEN EJECUTIVO CONSOLIDADO

| Área | Estado General | Hallazgos Críticos | Riesgo |
|------|---------------|-------------------|--------|
| **Cronjobs & Procesos** | ⚠️ Funcional con deuda técnica severa | 7 archivos de telemetría 95% duplicados, N+1 extremo, logs inexistentes | 🔴 Alto |
| **Seguridad & Auth** | ⚠️ Parcialmente seguro | Sin rate limiting, cookies sin Secure, SECRET_KEY placeholder, sin 2FA | 🔴 Alto |
| **Modelos & Base de Datos** | ⚠️ Diseño con bugs estructurales | `modified` nunca se actualiza, índices faltantes, inconsistencias migraciones | 🔴 Alto |
| **Admin & UI** | ✅ Muy avanzado | 14 modelos, 3 vistas custom, gráficos Chart.js, reportes PDF/Excel. Faltan: panel cronjobs, mapa, DGA queue UI | 🟡 Medio |

**Hallazgo transversal más grave:** El campo `modified` en el modelo base (`ModelApi`) usa `auto_now_add=True` en lugar de `auto_now=True`, lo que significa que **todas las tablas del sistema tienen `modified == created` permanentemente** — 13 modelos afectados.

---

## 1. CRONJOBS Y PROCESOS DE DATOS

### 1.1 Inventario (15 jobs activos)

| Job | Frecuencia | Estado |
|-----|-----------|--------|
| twin_f1 | Cada minuto | 🔴 Código duplicado, 150 logins/min a TDATA |
| twin_f5 | Cada 5 min | 🔴 Idem |
| twin_f10 | Cada 10 min | 🔴 Idem |
| twin (60) | Cada hora | 🔴 Idem |
| nettra_f5 | Cada 5 min | 🔴 Idem |
| nettra (60) | Cada hora | 🔴 Idem |
| novus (60) | Cada hora | 🔴 Idem |
| cron_dga | Cada 3 min | 🟡 Rate limit implícito, query por registro |
| cron_sma | Cada 5 min | 🟡 Token hardcodeado, solo punto 1 |
| cron_alerts | Cada 10 min | 🟢 Funcional, un query por alerta |
| space_backup | Cada hora | 🟢 Bien implementado |
| daily_bulletin | 01:00 diario | 🔴 N+1 masivo, itera todos los puntos |
| daily_chat_report | 12:00 diario | 🟡 Detección de resets en Python |
| daily_active_tickets | 13:00 diario | 🟡 Similar a chat report |
| dga_mayor_hourly | Cada hora :05 | 🟢 Funcional |

### 1.2 Problemas Críticos

**A. Duplicación Masiva (95% duplicado)**
Los 7 archivos de telemetría (`twin*.py`, `nettra*.py`, `novus.py`) suman **2.961 líneas** donde ~2.800 son idénticas. Solo cambia: frecuencia, getter por defecto, y validación de frecuencia (comentada en algunos).

**B. N+1 Queries Extremo**
Por cada punto → por cada variable → se ejecutan 3-4 queries a `InteractionDetail`:
```python
# Se repite por cada variable de cada punto
InteractionDetail.objects.filter(
    catchment_point_id=point["id"]
).order_by("-date_time_medition").first()
```

**C. Login TDATA por cada variable**
`get_data_tdata()` llama `get_token()` **en cada variable de cada punto**. Con 50 puntos × 3 variables = **150 logins/minuto** en `twin_f1`.

**D. Logs inexistentes**
El directorio `/tmp/smarthydro/` no existe. Todos los logs de cronjobs van a `/dev/null`.

### 1.3 Top 5 Mejoras de Alto Impacto / Bajo Esfuerzo

| # | Mejora | Esfuerzo Est. | Impacto |
|---|--------|--------------|---------|
| 1 | Cachear token TDATA durante ejecución del cronjob | 15 min | Elimina 150 logins/min |
| 2 | Crear `/tmp/smarthydro/` y rotar logs | 5 min | Visibilidad operativa |
| 3 | Agregar índice `(catchment_point, date_time_medition DESC)` | 15 min | Acelera todos los queries N+1 |
| 4 | Unificar 7 cronjobs de telemetría en runner parametrizado | 2-3h | Reduce 2.800 líneas duplicadas |
| 5 | Usar `select_related` en querysets iniciales de telemetría | 30 min | Elimina N+1 en relaciones |

---

## 2. SEGURIDAD Y AUTENTICACIÓN

### 2.1 Configuración HTTPS/SSL — Faltantes Críticos

| Configuración | Estado | Riesgo |
|---------------|--------|--------|
| `SECURE_SSL_REDIRECT` | ❌ No existe | HTTP→HTTPS no forzado |
| `SESSION_COOKIE_SECURE` | ❌ No existe | Cookie por HTTP sin cifrar |
| `CSRF_COOKIE_SECURE` | ❌ No existe | CSRF por HTTP |
| `SECRET_KEY` en `.env` | ⚠️ Placeholder (`tu_super_secret_key_aqui...`) | Debe rotarse |
| `X_FRAME_OPTIONS` | ⚠️ `DENY` en dev, `SAMEORIGIN` en prod | Debilita clickjacking en prod |

### 2.2 Autenticación

| Aspecto | Estado |
|---------|--------|
| Hashing | ✅ PBKDF2 (Django default) |
| Validación contraseña | ⚠️ Mínimo 8 chars, sin complejidad requerida |
| Rate limiting login | 🔴 **Inexistente** — fuerza bruta ilimitada |
| Rate limiting password reset | 🔴 **Inexistente** |
| 2FA / MFA | 🔴 **Inexistente** |
| Verificación email | 🔴 `is_verified=True` por defecto |

### 2.3 Secretos Expuestos

| Secreto | Ubicación |
|---------|-----------|
| Password DB cluster | `maintenance/analyze_cluster.py`, `backup_cluster.py` |
| Password API SMA | `api/cronjobs/sma/cron_sma.py:128` |
| Credenciales TDATA | `api/cronjobs/telemetry/getters/tdata.py` |
| Google Chat webhooks | `api/core/utils/google_chat.py:10-13` |
| `USER_DEFAULT_PASSWORD` | `.env` (`pozos.2023`) |
| `DGA_DEFAULT_PASSWORD` | `.env` (`ZSQgCiDg7y`) |
| `txt_password` (deprecated) | `core_user` tabla con default legacy |

### 2.4 CSP y CORS

- **CSP:** Configurado pero con `'unsafe-inline'` y `'unsafe-eval'` — anula gran parte de la protección XSS.
- **CORS:** Whitelist incluye `http://localhost:3000`, `:8000`, `:3001` en el mismo archivo de producción.

### 2.5 Top 5 Mejoras de Seguridad Prioritarias

| # | Mejora | Esfuerzo |
|---|--------|----------|
| 1 | Generar `SECRET_KEY` fuerte y rotar | 5 min |
| 2 | Agregar `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | 10 min |
| 3 | Mover credenciales hardcodeadas a variables de entorno | 1h |
| 4 | Implementar `AnonRateThrottle` en DRF para login | 30 min |
| 5 | Eliminar campo `txt_password` de `User` | 15 min (migración) |

---

## 3. MODELOS Y BASE DE DATOS

### 3.1 🚨 BUG CRÍTICO: `modified` nunca se actualiza

```python
# api/core/models/utils.py:15-18
modified = models.DateTimeField(
    auto_now_add=True,  # ❌ DEBE SER auto_now=True
)
```
**Impacto:** Todas las 13 tablas tienen `modified == created` permanentemente. Rompe auditoría, ordenamiento, y cualquier lógica que dependa de fecha de modificación.

### 3.2 Índices Faltantes Críticos

Los siguientes campos se filtran u ordenan frecuentemente pero **no tienen índice**:

| Tabla | Campo(s) | Justificación |
|-------|----------|---------------|
| `core_interactiondetail` | `send_dga` | Filtrado cada 3 min (cron DGA) |
| `core_interactiondetail` | `is_error` | Métricas de salud, reportes |
| `core_interactiondetail` | `days_not_conection` | Filtros de conectividad |
| `core_interactiondetail` | `created` | `total.py`, reportes diarios |
| `core_interactiondetail` | `(catchment_point, created)` | Filtros combinados constantes |
| `core_interactiondetail` | `total_diff` | Reporte puntos "stuck" |
| `core_profiledataconfigcatchment` | `is_telemetry` | Altamente filtrado |
| `core_variable` | `type_variable` | Búsquedas: NIVEL, CAUDAL, etc. |
| `core_notificationscatchment` | `(is_active, is_read)` | Dashboard notificaciones |

### 3.3 Parámetros Inválidos en Campos

| Campo | Parámetro Inválido | Django lo ignora silenciosamente |
|-------|-------------------|----------------------------------|
| `InteractionDetail.date_time_medition` | `max_length=800` | DateTimeField no acepta max_length |
| `InteractionDetail.date_time_last_logger` | `max_length=800` | DateTimeField no acepta max_length |
| `DgaDataConfigCatchment.flow_granted_dga` | `max_length=1200` | DecimalField no acepta max_length |

### 3.4 Inconsistencia Migraciones vs Modelos

La migración `0001_initial` creó:
- `flow` → `CharField(max_length=400)`
- `nivel` → `CharField(max_length=400)`
- `water_table` → `CharField(max_length=400)`

El modelo actual define:
- `flow` → `DecimalField(max_digits=5, decimal_places=2)`
- `nivel` → `DecimalField(...)`
- `water_table` → `DecimalField(...)`

**Faltan migraciones** para aplicar estos cambios de tipo.

### 3.5 Crecimiento de Tablas

| Tabla | Crecimiento | Riesgo |
|-------|------------|--------|
| `core_interactiondetail` | 1,000-10,000+ registros/día | 🔴 Particionamiento eventual necesario |
| `core_notificationscatchment` | Medio | 🟡 |
| `core_filecatchment` | Medio (archivos en disco) | 🟡 |

### 3.6 Top 5 Mejoras de Base de Datos

| # | Mejora | Esfuerzo |
|---|--------|----------|
| 1 | Corregir `modified` → `auto_now=True` + migración | 10 min |
| 2 | Crear índices faltantes (sección 3.2) | 30 min |
| 3 | Crear índice parcial `send_dga=True` en InteractionDetail | 10 min |
| 4 | Limpiar parámetros `max_length` inválidos | 10 min |
| 5 | Revisar migraciones faltantes para `flow`, `nivel`, `water_table` | 30 min |

---

## 4. ADMIN Y UI

### 4.1 Estado Actual (Muy Avanzado)

- **14 modelos** registrados, todos con import/export
- **3 vistas custom:** Dashboard, Monitoreo de Telemetría, Status del Sistema
- **Reportes:** PDF y Excel desde acciones de admin
- **Gráficos:** Chart.js en changelist y dashboard
- **Filtros complejos** con badges de estado en HTML enriquecido

### 4.2 Funcionalidades Destacadas

| Funcionalidad | Estado |
|---------------|--------|
| Dashboard telemetría (métricas veracidad/DGA) | ✅ Implementado |
| Monitoreo de alertas en tiempo real | ✅ Implementado |
| Import/export masivo | ✅ django-import-export |
| Indicadores en changelist | ✅ Custom |
| Reportes PDF/Excel | ✅ Generados desde admin |

### 4.3 Funcionalidades Faltantes (Oportunidades)

| # | Funcionalidad | Impacto |
|---|---------------|---------|
| 1 | **Panel de gestión de cola DGA** | Hoy solo por API, no hay UI visual |
| 2 | **Panel de logs de cronjobs** | Logs en archivos del servidor, inaccesibles desde admin |
| 3 | **Mapa de puntos (lat/lon)** | Campos existen pero no se visualizan |
| 4 | **Configuración masiva de puntos** | Batch edits no disponibles |
| 5 | **Sistema de tickets/incidencias** | Integrado a notificaciones |
| 6 | **Wizard de creación de puntos** | Flujo guiado para nuevos puntos |
| 7 | **Auditoría/historial de cambios** | `modified` roto, sin historial de versiones |

---

## 5. MATRIZ DE PRIORIDAD: ACCIONES RÁPIDAS (1 día de trabajo)

Las siguientes acciones, si se ejecutan en orden, pueden realizarse en **menos de 1 día** y resolverían la mayoría de los problemas críticos:

### Fase 1: Seguridad Inmediata (1-2 horas)
1. ✅ Generar `SECRET_KEY` fuerte
2. ✅ Agregar `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
3. ✅ Mover credenciales hardcodeadas a `.env`

### Fase 2: Corrección de Bug Crítico (30 min)
4. ✅ Corregir `modified` → `auto_now=True` + migración

### Fase 3: Índices de Base de Datos (1 hora)
5. ✅ Crear índices faltantes en `InteractionDetail`
6. ✅ Crear índice parcial `send_dga=True`

### Fase 4: Optimización de Cronjobs (2-3 horas)
7. ✅ Cachear token TDATA
8. ✅ Crear directorio de logs `/tmp/smarthydro/`
9. ✅ Agregar `select_related` en telemetría

**Total estimado: 5-7 horas de trabajo**

---

## 6. RIESGOS ACUMULADOS POR NO ACTUAR

| Riesgo | Probabilidad | Impacto | Escenario |
|--------|------------|---------|-----------|
| Fuerza bruta en login | Alta | Crítico | Cuenta admin comprometida |
| SECRET_KEY débil | Media | Crítico | Firma JWT vulnerable |
| N+1 queries + crecimiento | Alta | Alto | DB sobrecargada, timeouts |
| Credenciales expuestas en repo | Media | Crítico | Acceso no autorizado a APIs externas |
| Sin logs de cronjobs | Alta | Medio | Fallas silenciosas no detectadas |
| `modified` roto | Alta | Medio | Sin auditoría de cambios |
| `InteractionDetail` sin índices | Alta | Alto | Escaneos secuenciales en tablas grandes |

---

## 7. CONCLUSIÓN

El sistema **SmartHydro funciona operativamente** pero acumula **deuda técnica significativa** concentrada en:

1. **Duplicación masiva de código** (2.800 líneas duplicadas en telemetría)
2. **N+1 queries extremo** que escalará mal con más puntos
3. **Configuraciones de seguridad faltantes** (SSL redirect, Secure cookies, rate limiting)
4. **Bug estructural en modelo base** (`modified` nunca actualiza)
5. **Índices de BD insuficientes** para el volumen de datos
6. **Secretos expuestos** en múltiples archivos

**La buena noticia:** La mayoría de los problemas críticos tienen soluciones de **bajo esfuerzo y alto impacto**. Con ~1 día de trabajo enfocado se puede estabilizar significativamente el sistema.

**La segunda buena noticia:** El admin de Django está muy evolucionado y el stack técnico (Django 4.2, PostgreSQL 15, Redis) es sólido. No hay que reescribir nada, solo consolidar y asegurar.

---

*Generado automáticamente por análisis de código. Sin modificaciones realizadas.*
