# Catálogo de Riesgos — SmartHydro

> **Propósito:** listar los componentes que no deben tocarse sin análisis y pruebas exhaustivas, ya que están en producción activa y afectan telemetría, alertas a clientes y envíos a DGA/SMA.

---

## 🔴 Críticos — No modificar sin plan detallado y aprobación explícita

| # | Componente | Ubicación | Riesgo si se altera |
|---|------------|-----------|---------------------|
| 1 | **Cálculo de totales unificado** | `api/cronjobs/telemetry/controllers/total.py` | Pérdida de monotonicidad de pulsos, totales incorrectos, envíos DGA/SMA erróneos. |
| 2 | **Getter TDATA** | `api/cronjobs/telemetry/getters/tdata.py` | Credenciales hardcodeadas (pendiente de mover a env). Cambios pueden romper telemetría TWIN. |
| 3 | **Modelos de punto y telemetría** | `api/core/models/catchment_points.py`, `interaction_detail.py` | Migraciones masivas, inconsistencia de datos históricos. |
| 4 | **Señales de notificaciones** | `api/core/signals/notifications.py` | Alertas a clientes podrían dejar de enviarse o duplicarse. |
| 5 | **Envío DGA** | `api/cronjobs/dga/send_data_dga.py`, `caudal_calculations.py` | Incumplimiento regulatorio, multas. |
| 6 | **Envío SMA** | `api/cronjobs/sma/cron_sma.py` | Incumplimiento regulatorio. |
| 7 | **Particionamiento InteractionDetail** | Migraciones `0059`, `0066`, `0067` | Uso de SQL específico de PostgreSQL. Cambios pueden romper tests SQLite o replicación. |

---

## 🟠 Altos — Requieren tests de regresión antes y después

| # | Componente | Ubicación | Riesgo |
|---|------------|-----------|--------|
| 8 | **Endpoints legacy** | `api/core/views/catchment_points.py`, `interaction_detail.py`, `management.py` | Clientes existentes dependen de sus contratos de respuesta. |
| 9 | **Serializers legacy** | `api/core/serializers/` | Cambios en campos expuestos rompen frontend. |
| 10 | **Throttling Ikolu** | `api/api_ik/throttles.py` | Ajustes pueden bloquear apps móviles. |
| 11 | **Crontab unificado** | `api/cronjobs/telemetry/telemetry_unified.py` | Paralelismo entre twin/nettra/novus. Cambios afectan recepción de datos. |
| 12 | **Alert engine/dispatcher** | `api/cronjobs/alerts/` | Falsos positivos/negativos en alertas. |
| 13 | **Telemetry reprocessor** | `api/core/views/telemetry_reprocessor_api.py` | Modificaciones incorrectas pueden corromper datos históricos. |

---

## 🟡 Medios — Precaución estándar de producción

| # | Componente | Ubicación | Riesgo |
|---|------------|-----------|--------|
| 14 | **Admin custom** | `api/core/admin_views.py`, `admin.py` | Cambios afectan operadores internos. |
| 15 | **Reportes Excel/PDF** | `api/core/reports/` | Cambios en formatos afectan entregables a clientes. |
| 16 | **Settings de seguridad** | `api/settings.py` | Ajustes incorrectos pueden romper HTTPS, CSP o sesiones. |
| 17 | **Docker Compose** | `docker-compose.production.secure.yml` | Puede afectar disponibilidad de servicios. |
| 18 | **Backups y cronjobs de cluster** | `api/cronjobs/cluster_backup*.py`, `space_backup.py` | Riesgo de pérdida de datos si fallan. |

---

## ✅ Zona segura para innovar (nuevas funcionalidades)

| Área | Justificación |
|------|---------------|
| Nuevas apps (`crm`, `subscriptions`, `ai_agents`) | No interfieren con legacy si se integran mediante servicios. |
| Nuevos endpoints bajo `/api/ik/` | Namespace separado, no rompe `/api/`. |
| Celery tasks nuevos | Pueden correr en paralelo a crontab legacy con feature flags. |
| Scripts de auditoría y análisis | No afectan runtime. |
| Documentación (`docs/audit/`) | Solo lectura/análisis. |

---

## Reglas de oro para cualquier cambio

1. **Tests de regresión y DGA deben pasar** antes de mergear.
2. **No editar migraciones ya aplicadas** en producción.
3. **No hardcodear credenciales** ni tokens.
4. **No hacer `docker-compose down`** sin confirmación explícita.
5. **Backup de base de datos** antes de aplicar migraciones en producción.
6. **Feature flags** para activar/desactivar comportamiento nuevo sin deploy de emergencia.
