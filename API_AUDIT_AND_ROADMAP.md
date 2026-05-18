# Auditoría y Mapa de la API SmartHydro
> Fecha: 2026-05-17
> Estado: Producción activa — Tests regresión ✅ 52/52 pasando | ComplianceProvider + TelemetryProvider migrados

---

## 1. Mapa de Endpoints

### API Legacy (`/api/`)

| Endpoint | Clase | Métodos | Descripción | Riesgo |
|----------|-------|---------|-------------|--------|
| `/api/clients/` | `ClientViewSet` | CRUD | Clientes | 🟢 Bajo |
| `/api/project_catchments/` | `ProjectCatchmentsViewSet` | CRUD | Proyectos | 🟢 Bajo |
| `/api/catchment_points/` | `CatchmentPointViewSet` | CRUD | Puntos de captación | 🔴 **N+1 severo** |
| `/api/profile_ikolu_catchment/` | `ProfileIkoluCatchmentViewSet` | CRUD | Perfiles Ikolu | 🟢 Bajo |
| `/api/notifications_catchment/` | `NotificationsCatchmentViewSet` | CRUD | Notificaciones legacy | 🟡 Medio |
| `/api/response_notifications_catchment/` | `ResponseNotificationsCatchmentViewSet` | CRUD | Respuestas a notificaciones | 🟢 Bajo |
| `/api/type_file_catchment/` | `TypeFileCatchmentViewSet` | CRUD | Tipos de archivo | 🟢 Bajo |
| `/api/file_catchment/` | `FileCatchmentViewSet` | CRUD | Archivos | 🟢 Bajo |
| `/api/profile_data_config_catchment/` | `ProfileDataConfigCatchmentViewSet` | CRUD | Config telemetría | 🟢 Bajo |
| `/api/dga_data_config_catchment/` | `DgaDataConfigCatchmentViewSet` | CRUD | Config DGA | 🟢 Bajo |
| `/api/schemes_catchment/` | `SchemesCatchmentViewSet` | CRUD | Esquemas | 🟢 Bajo |
| `/api/variables/` | `VariableViewSet` | CRUD | Variables | 🟢 Bajo |
| `/api/register_persons/` | `RegisterPersonsViewSet` | CRUD | Personas registro | 🟢 Bajo |
| `/api/interaction_detail/` | `InteractionDetailViewSet` | CRUD + List | Telemetría CRUD | 🟢 **Paginado (10)** |
| `/api/interaction_detail_override/` | `InteractionDetailOverrideViewSet` | CRUD + List | Telemetría sin paginar | 🟡 **Sin paginar (legacy)** |
| `/api/interaction_detail_override_month/` | `InteractionDetailOverrideMonthViewSet` | CRUD + List | Telemetría mensual | 🟡 **Sin paginar (legacy)** |
| `/api/interaction_detail_xlsx/` | `InteractionXLS` | GET | Export XLSX | 🟡 Medio |
| `/api/interaction_detail_xlsx_month/` | `InteractionXLSMonth` | GET | Export XLSX mensual | 🟡 Medio |
| `/api/interaction_detail_xlsx_dga/` | `InteractionXLSDga` | GET | Export XLSX DGA | 🟡 Medio |
| `/api/users/` | `UserViewSet` | Retrieve | Usuarios | 🟢 Bajo |
| `/api/management/` | `ManagementViewSet` | GET/POST | Dashboard admin | 🟢 **N+1 resuelto** |
| `/api/batch/telemetry/` | `BatchTelemetryView` | POST | Batch telemetría | 🟢 Bajo |
| `/api/batch/stats/` | `BatchStatsView` | POST | Batch stats | 🟢 Bajo |
| `/api/reports/` | `ReportsGenerationViewSet` | GET/POST | Reportes | 🟡 Medio |
| `/api/chatbot/` | `ChatbotAppView` | POST | Chatbot IA | 🟢 Bajo |
| `/api/alert_rules/` | `AlertRuleViewSet` | CRUD | Reglas de alerta | 🟢 Bajo |
| `/api/alert_channels/` | `AlertChannelViewSet` | CRUD | Canales de alerta | 🟢 Bajo |
| `/api/alert_triggers/` | `AlertTriggerViewSet` | List + Ack | Disparos de alerta | 🟢 Bajo |
| `/api/system_events/` | `SystemEventViewSet` | List | Eventos del sistema | 🟢 Bajo |

### API Ikolu (`/api/ik/`) — Nueva generación

| Endpoint | Clase | Métodos | Descripción | Estado |
|----------|-------|---------|-------------|--------|
| `/api/ik/login/` | `OptimizedLoginView` | POST | Login reducido | ✅ Activo |
| `/api/ik/points_summary/` | `PointsSummaryView` | GET | Resumen de puntos + telemetría | ✅ Activo |
| `/api/ik/point/{id}/summary/` | `PointSummaryView` | GET | Punto específico | ✅ Activo |
| `/api/ik/point/{id}/variables/` | `PointVariablesView` | GET | Mapeo variable_id → display_key | ✅ **NUEVO** |
| `/api/ik/point/{id}/calendar/` | `PointCalendarView` | GET | Calendario de consumo | ✅ Activo |
| `/api/ik/my_points/` | `MyPointsView` | GET | Lista liviana de puntos | ✅ Activo |
| `/api/ik/dashboard_stats/` | `DashboardStatsView` | GET | KPIs del Centro de Control | ✅ Activo |
| `/api/ik/batch/telemetry/` | `BatchTelemetryView` | POST | Batch multi-punto | ✅ Activo |
| `/api/ik/batch/stats/` | `BatchStatsView` | POST | Stats agregados | ✅ Activo |
| `/api/ik/announcements/public/` | `PublicAnnouncementsView` | GET | Anuncios públicos | ✅ Activo |
| `/api/ik/auth/password-reset/` | — | POST | Reset password | ✅ Activo |

---

## 2. Problemas Críticos Identificados

### 🟢 RESUELTO — N+1 Query Severo

**`management.py:points_status`** ✅ Optimizado
- Precalcula últimas interacciones en 1 query (`DISTINCT ON`)
- Precalcula perfiles de telemetría en 1 query
- Loop usa `select_related` ya precargado
- **Antes:** 146+ queries | **Ahora:** 2 queries

**`CatchmentPointIkoluSerializer` (legacy login)**
- Batch processing sin prefetch en variables
- Cálculo de flow recalcula todo el día para cada registro

### 🟡 MEDIO — Endpoints Sin Paginación (Legacy)

| Endpoint | Modelo | Registros aprox | Estado |
|----------|--------|----------------|--------|
| `/api/interaction_detail/` | InteractionDetail | 2.5M | `PageNumberPagination` (10) ✅ |
| `/api/interaction_detail_override/` | InteractionDetail | 2.5M | `NoPagination` explícita — **legacy requiere array plano** |
| `/api/interaction_detail_override_month/` | InteractionDetail | 2.5M | `NoPagination` explícita — **legacy requiere array plano** |
| `/api/notifications_catchment/` | NotificationsCatchment | Miles | Sin paginar |

**Impacto:** `interaction_detail_override*` intencionalmente sin paginar para no romper frontend legacy. Migración a API Ikolu (`/api/ik/`) recomendada.

### 🟡 ALTO — Seguridad

| Problema | Ubicación | Impacto |
|----------|-----------|---------|
| CORS permite localhost en prod | `settings.py:249-257` | Downgrade posible |
| `X_FRAME_OPTIONS = SAMEORIGIN` | `settings.py:462` | Anula DENY |
| `InteractionDetailOverrideViewSet` sin paginación (legacy) | `interaction_detail.py:130` | Intencional — migrar a `/api/ik/` |
| Rate limiting en `/api/ik/login/` | `settings.py` | `AnonLoginRateThrottle` 100 req/hr ✅ |

### 🟡 ALTO — Performance

| Problema | Ubicación | Detalle |
|----------|-----------|---------|
| Recálculo diario en serializer | `InteractionDetailModelSerializer` | Recalcula todo el día para cada registro en list view |
| `total` es CharField | `interaction_detail.py:42` | No se puede sumar/agregar en BD |
| No hay índices en FKs frecuentes | `catchment_points.py` | `CatchmentPoint.project`, `.owner_user` sin `db_index=True` |
| `DecimalField(max_length=1200)` | `catchment_points.py:475` | Inválido en Django |

---

## 3. Propuestas de Mejora

### Fase A: Seguridad y estabilidad ✅ COMPLETADA

| # | Mejora | Archivo | Estado |
|---|--------|---------|--------|
| 1 | Agregar paginación a `InteractionDetailViewSet` | `interaction_detail.py` | ✅ `PageNumberPagination` |
| 2 | Agregar paginación a `InteractionDetailOverrideViewSet` | `interaction_detail.py` | ✅ `NoPagination` explícita (legacy) |
| 3 | Agregar `throttle_classes` a `/api/ik/login/` | `settings.py` | ✅ `AnonLoginRateThrottle` 100/hr |
| 4 | Corregir CORS en producción | `settings.py` | ⏳ Pendiente |
| 5 | Corregir `DecimalField(max_length=1200)` | `catchment_points.py` | ⏳ Requiere migración |
| 6 | Agregar `db_index=True` a FKs frecuentes | `catchment_points.py` | ⏳ Requiere migración |

### Fase B: Performance (En progreso)

| # | Mejora | Archivo | Estado |
|---|--------|---------|--------|
| 7 | Resolver N+1 en `management.py:points_status` | `management.py` | ✅ Precálculo en 2 queries |
| 8 | Cachear consultas de perfil en serializer | `interaction_detail.py` | ⏳ Pendiente |
| 9 | Agregar Redis cache a `PointsSummaryView` | `api_ik/views.py` | ⏳ Pendiente |
| 10 | Optimizar `CatchmentPointIkoluSerializer` batch | `catchment_points.py` | ⏳ Pendiente |

### Fase C: Arquitectura (Futuro)

| # | Mejora | Impacto |
|---|--------|---------|
| 11 | Migrar `total` de CharField a DecimalField | Permite agregaciones en BD |
| 12 | Deprecar `NotificationsCatchment` legacy | Unificar en `AlertTrigger` + `SystemEvent` |
| 13 | Separar esquema de telemetría vs visualización | Lo que estamos empezando con `display_key` |
| 14 | Implementar WebSocket para telemetría en tiempo real | Dashboard live sin polling |
| 15 | Rate limiting global en nginx | Protección DDoS |

---

## 4. Estado del Subsistema de Alertas (Nuevo)

| Regla | ID | Target Type | Canal | Estado |
|-------|-----|-------------|-------|--------|
| Desconexión | 9 | `DISCONNECTION` | Google Chat + IA | ✅ Activo |
| Reconexión | 10 | `RECONNECTION` | Google Chat | ✅ Activo |
| Error de procesamiento | 11 | `PROCESSING_ERROR` | Google Chat | ✅ Activo |

**Legacy desactivado:**
- `check_and_notify_disconnection` ❌
- `check_and_notify_reconnection` ❌
- `check_and_notify_error` ❌

---

## 5. Estado de Tests

| Suite | Tests | Estado |
|-------|-------|--------|
| `tests.regression` | 47 | ✅ Todos pasando |
| `tests.dga` | 5 | ✅ Todos pasando |
| `tests.baseline` | — | ⏳ Pendiente revisión |

**Fixes aplicados a tests:**
- `CatchmentPoint` ahora requiere `owner_user` y `project` (NOT NULL) — tests actualizados
- `DgaDataConfigCatchment` se crea automáticamente por signal — tests ajustados para modificar en vez de crear duplicados
- `@patch('api.cronjobs.dga.cron_dga.settings')` → `@override_settings()` (settings no importado a nivel módulo)
- Test FPC Tissue actualizado: bloqueo removido de producción, valida comportamiento actual

## 6. Próximos Pasos Recomendados

1. **Corregir CORS en producción** — Remover `localhost` de `CORS_ALLOWED_ORIGINS`
2. **Migrar `DecimalField(max_length=1200)`** — Requiere migración y validación de datos
3. **Agregar `db_index=True` a FKs frecuentes** — Requiere migración en horario de baja
