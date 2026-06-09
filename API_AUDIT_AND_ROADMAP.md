# Auditoría y Mapa de la API SmartHydro
> Fecha: 2026-06-03
> Estado: Producción activa — Tests regresión ✅ 120/120 pasando | ComplianceProvider + TelemetryProvider migrados

---

## 1. Mapa de Endpoints

### API Legacy (`/api/`)

| Endpoint | Clase | Métodos | Descripción | Riesgo |
|----------|-------|---------|-------------|--------|
| `/api/client/` | `ClientViewSet` | CRUD | Clientes | 🟢 Bajo |
| `/api/project_catchments/` | `ProjectCatchmentsViewSet` | CRUD | Proyectos | 🟢 Bajo |
| `/api/catchment_points/` | `CatchmentPointViewSet` | CRUD | Puntos de captación | 🟡 N+1 parcialmente resuelto |
| `/api/profile_ikolu_catchment/` | `ProfileIkoluCatchmentViewSet` | CRUD | Perfiles Ikolu | 🟢 Bajo |
| `/api/notifications_catchment/` | `NotificationsCatchmentViewSet` | CRUD | Notificaciones legacy | 🟡 Medio (en deprecación) |
| `/api/response_notifications_catchment/` | `ResponseNotificationsCatchmentViewSet` | CRUD | Respuestas a notificaciones | 🟢 Bajo (con adapter a AlertTrigger) |
| `/api/type_file_catchment/` | `TypeFileCatchmentViewSet` | CRUD | Tipos de archivo | 🟢 Bajo |
| `/api/file_catchment/` | `FileCatchmentViewSet` | CRUD | Archivos | 🟢 Bajo |
| `/api/profile_data_config_catchment/` | `ProfileDataConfigCatchmentViewSet` | CRUD | Config telemetría | 🟢 Bajo |
| `/api/dga_data_config_catchment/` | `DgaDataConfigCatchmentViewSet` | CRUD | Config DGA | 🟢 Bajo |
| `/api/schemes_catchment/` | `SchemesCatchmentViewSet` | CRUD | Esquemas | 🟢 Bajo |
| `/api/variable/` | `VariableViewSet` | CRUD | Variables | 🟢 Bajo |
| `/api/register_persons/` | `RegisterPersonsViewSet` | CRUD | Personas registro | 🟢 Bajo |
| `/api/interaction_detail_json/` | `InteractionDetailViewSet` | CRUD + List | Telemetría CRUD (JSON) | 🟢 Paginado (10) |
| `/api/interaction_detail/` | `InteractionXLS` | GET | Export XLSX telemetría | 🟢 Bajo |
| `/api/interaction_detail_dga/` | `InteractionXLSDga` | GET | Export XLSX DGA | 🟢 Bajo |
| `/api/interaction_detail_override/` | `InteractionDetailOverrideViewSet` | CRUD + List | Override telemetría | 🟡 Sin paginar (legacy intencional) |
| `/api/interaction_detail_override_month/` | `InteractionDetailOverrideMonthViewSet` | CRUD + List | Override mensual | 🟡 Sin paginar (legacy intencional) |
| `/api/interaction_detail_override_month_xlsx/` | `InteractionXLSMonth` | GET | Export XLSX mensual | 🟢 Bajo |
| `/api/users/` | `UserViewSet` | Retrieve | Usuarios | 🟢 Bajo |
| `/api/management/system_status/` | `ManagementViewSet` | GET | Estado general | 🟢 Bajo |
| `/api/management/points_status/` | `ManagementViewSet` | GET | Estado de puntos | 🟢 N+1 resuelto (2 queries) |
| `/api/management/telemetry_metrics/` | `ManagementViewSet` | GET | Métricas de telemetría | 🟢 Bajo |
| `/api/management/dga_queue_status/` | `ManagementViewSet` | GET | Cola DGA | 🟢 Bajo |
| `/api/management/clear_dga_queue/` | `ManagementViewSet` | POST | Limpiar cola DGA | 🟢 Bajo |
| `/api/management/requeue_dga/` | `ManagementViewSet` | POST | Reencolar DGA | 🟢 Bajo |
| `/api/management/toggle_telemetry/` | `ManagementViewSet` | POST | Toggle telemetría | 🟢 Bajo |
| `/api/management/update_point_frequency/` | `ManagementViewSet` | POST | Cambiar frecuencia | 🟢 Bajo |
| `/api/management/notifications_summary/` | `ManagementViewSet` | GET | Resumen notificaciones | 🟢 Bajo |
| `/api/management/system_map/` | `ManagementViewSet` | GET | Mapa del sistema | 🟢 Staff only |
| `/api/management/resources_status/` | `ManagementViewSet` | GET | Estado recursos servidor | 🟢 Staff only |
| `/api/reports/` | `ReportsGenerationViewSet` | GET | Reportes Excel + JSON | 🟢 Bajo |
| `/api/chat/` | `ChatbotAppView` | POST | Chatbot IA app | 🟢 Bajo |
| `/api/alert_rules/` | `AlertRuleViewSet` | CRUD | Reglas de alerta | 🟢 Bajo |
| `/api/alert_channels/` | `AlertChannelViewSet` | CRUD | Canales de alerta | 🟢 Bajo |
| `/api/alert_triggers/` | `AlertTriggerViewSet` | List + Ack | Disparos de alerta | 🟢 Bajo |
| `/api/system_events/` | `SystemEventViewSet` | List | Eventos del sistema | 🟢 Bajo |
| `/api/telemetry_providers/` | `TelemetryProviderViewSet` | GET | Proveedores telemetría | 🟢 Solo lectura |
| `/api/compliance_providers/` | `ComplianceProviderViewSet` | GET | Proveedores compliance | 🟢 Solo lectura |
| `/api/counter_reset_logs/` | `CounterResetLogViewSet` | GET | Logs reset contadores | 🟢 Solo lectura |

### API Ikolu (`/api/ik/`) — Centro de Control

| Endpoint | Clase | Métodos | Descripción | Estado |
|----------|-------|---------|-------------|--------|
| `/api/ik/login/` | `OptimizedLoginView` | POST | Login reducido | ✅ Activo |
| `/api/ik/points_summary/` | `PointsSummaryView` | GET | Resumen de puntos + telemetría | ✅ Activo |
| `/api/ik/point/<id>/summary/` | `PointSummaryView` | GET | Punto específico | ✅ Activo |
| `/api/ik/point/<id>/variables/` | `PointVariablesView` | GET | Mapeo variable_id → display_key | ✅ Activo |
| `/api/ik/point/<id>/calendar/` | `PointCalendarView` | GET | Calendario de consumo | ✅ Activo |
| `/api/ik/point/<id>/records/` | `PointRecordsView` | GET | Registros telemetría por rango | ✅ Activo |
| `/api/ik/point/<id>/config/` | `PointConfigView` | GET | Config liviana del punto | ✅ Activo |
| `/api/ik/point/<id>/gaps/` | `PointGapsView` | GET | Gap detection | ✅ Activo |
| `/api/ik/my_points/` | `MyPointsView` | GET | Lista liviana de puntos | ✅ Activo |
| `/api/ik/dashboard_stats/` | `DashboardStatsView` | GET | KPIs del Centro de Control | ✅ Activo |
| `/api/ik/compliance/` | `ComplianceListView` | GET | Compliance DGA/SMA detallado | ✅ Activo |
| `/api/ik/batch/telemetry/` | `BatchTelemetryView` | POST | Batch multi-punto | ✅ Activo |
| `/api/ik/batch/stats/` | `BatchStatsView` | POST | Stats agregados multi-punto | ✅ Activo |
| `/api/ik/announcements/public/` | `PublicAnnouncementsView` | GET | Anuncios públicos | ✅ Activo |
| `/api/ik/auth/password-reset/` | ResetPasswordRequestToken | POST | Reset password | ✅ Activo |
| `/api/ik/auth/password-reset/confirm/` | ResetPasswordConfirm | POST | Confirmar reset | ✅ Activo |
| `/api/ik/auth/password-reset/validate/` | ResetPasswordValidateToken | POST | Validar token | ✅ Activo |
| `/api/ik/tickets/` | `TicketsListCreateView` | GET/POST | Listar/crear tickets | ✅ Activo |
| `/api/ik/tickets/<id>/` | `TicketDetailUpdateView` | GET/PATCH | Ver/actualizar ticket | ✅ Activo |
| `/api/ik/tickets/<id>/comments/` | `TicketCommentsView` | GET/POST | Comentarios | ✅ Activo |
| `/api/ik/tickets/<id>/assign/` | `TicketAssignView` | POST | Asignar ticket | ✅ Activo |
| `/api/ik/tickets/<id>/status/` | `TicketStatusChangeView` | POST | Cambiar estado | ✅ Activo |
| `/api/ik/tickets/<id>/attachments/` | `TicketAttachmentsView` | GET/POST | Adjuntos | ✅ Activo |
| `/api/ik/tickets/stats/` | `TicketStatsView` | GET | Estadísticas de tickets | ✅ Activo |
| `/api/ik/telemetry/backfill/` | `TelemetryBackfillView` | POST | Backfill histórico | ✅ Activo |
| `/api/ik/chat/client/general_stats/` | `ClientStatsChatView` | POST | Chat interpretativo con Gemini | ✅ Activo |
| `/api/ik/system-events/summary/` | `SystemEventsSummaryView` | GET | Resumen eventos del sistema | ✅ Activo |

### Endpoints Sueltos

| Endpoint | Método | Descripción | Auth |
|----------|--------|-------------|------|
| `/` | GET | Info del servicio | AllowAny |
| `/health/` | GET | Health check | AllowAny |
| `/status/` | GET | Status JSON (DB, Redis, cronjobs) | login_required |
| `/status/dashboard/` | GET | HTML dashboard de status | login_required |
| `/reports/active-points/` | GET | Excel puntos activos | IsAuthenticated |
| `/compliance/dga/verify/` | GET | Verificar comprobante DGA | IsAuthenticated |
| `/api/chat-bot/` | POST | Webhook Google Chat | Google Chat token |
| `/api/schema/` | GET | OpenAPI Schema | AllowAny |
| `/api/schema/swagger-ui/` | GET | Swagger UI | AllowAny |
| `/api/schema/redoc/` | GET | Redoc | AllowAny |
| `/admin/dashboard/` | GET | Admin dashboard custom | Staff |
| `/admin/telemetry-monitoring/` | GET | Monitoreo telemetría HTML | Staff |
| `/admin/telemetry-monitoring/api/` | GET | API JSON monitoring grid | Staff |
| `/admin/telemetry-monitoring/api/point/<id>/records/` | GET | Registros punto monitoring | Staff |
| `/admin/dga-compliance-report/` | GET | Reporte compliance DGA | Staff |

---

## 2. Estado de Problemas Críticos

### 🟢 RESUELTO — N+1 Query Severo

**`management.py:points_status`** ✅ Optimizado (2026-05)
- Precalcula últimas interacciones en 1 query (`DISTINCT ON`)
- Precalcula perfiles de telemetría en 1 query
- **Antes:** 146+ queries | **Ahora:** 2 queries

### 🟢 RESUELTO — Seguridad

| Problema | Estado | Detalle |
|----------|--------|---------|
| `SESSION_COOKIE_SECURE = False` | ✅ Fix aplicado | `SESSION_COOKIE_SECURE = True` |
| `CSRF_COOKIE_SECURE = False` | ✅ Fix aplicado | `CSRF_COOKIE_SECURE = True` |
| `SECURE_SSL_REDIRECT = False` | ✅ Fix aplicado | `SECURE_SSL_REDIRECT = True` |
| Tokens impresos en logs | ✅ Fix aplicado | Removidos de `tdata.py` y `thingsio.py` |
| Redis sin autenticación | ✅ Fix aplicado | `requirepass` activado en todos los contenedores |
| Crontab duplicados | ✅ Fix aplicado | Limpieza completa (16 líneas vs 61+) |

### 🟡 MEDIO — Endpoints Sin Paginación (Legacy intencional)

| Endpoint | Modelo | Estado |
|----------|--------|--------|
| `/api/interaction_detail_json/` | InteractionDetail | `PageNumberPagination` (10) ✅ |
| `/api/interaction_detail_override/` | InteractionDetail | `NoPagination` explícita — legacy requiere array plano |
| `/api/interaction_detail_override_month/` | InteractionDetail | `NoPagination` explícita — legacy requiere array plano |
| `/api/notifications_catchment/` | NotificationsCatchment | Sin paginar (legacy) |

**Impacto:** `interaction_detail_override*` intencionalmente sin paginar para no romper frontend legacy. Migración a API Ikolu (`/api/ik/`) recomendada para nuevos desarrollos.

### 🟡 ALTO — Seguridad pendiente

| Problema | Ubicación | Impacto |
|----------|-----------|---------|
| CORS permite localhost en prod | `settings.py:249-257` | Downgrade posible |
| `X_FRAME_OPTIONS = SAMEORIGIN` | `settings.py:462` | Anula DENY |
| Credenciales TDATA hardcodeadas | `getters/tdata.py:12-13` | Riesgo de fuga |

### 🟡 ALTO — Performance pendiente

| Problema | Ubicación | Detalle |
|----------|-----------|---------|
| Recálculo diario en serializer | `InteractionDetailModelSerializer` | Recalcula todo el día para cada registro en list view |
| `total` es CharField | `interaction_detail.py` | No se puede sumar/agregar en BD |

---

## 3. Propuestas de Mejora

### Fase A: Seguridad y estabilidad ✅ COMPLETADA

| # | Mejora | Archivo | Estado |
|---|--------|---------|--------|
| 1 | Agregar paginación a `InteractionDetailViewSet` | `interaction_detail.py` | ✅ `PageNumberPagination` |
| 2 | Agregar `throttle_classes` a `/api/ik/login/` | `settings.py` | ✅ `LoginRateThrottle` 100/hr |
| 3 | Corregir `DecimalField(max_length=1200)` | `catchment_points.py` | ✅ Corregido en migraciones recientes |
| 4 | Ampliar `DecimalField(max_digits=5→10)` | `InteractionDetail` | ✅ Fix aplicado |
| 5 | Fix monotonicidad total | `controllers/total.py` + backfill | ✅ 1,786 registros NULL corregidos + 134 NOVUS |
| 6 | Fix race condition totales | `controllers/total.py` | ✅ `select_for_update()` + `F()` expressions |
| 7 | Fix reconexión bypass | `controllers/total.py` | ✅ `is_reconnection=True` ya no salta detección de reset |
| 8 | Fix `variable_details` honesto | getters | ✅ `success=True` solo cuando el getter trae datos |
| 9 | Índice compuesto DGA | migraciones | ✅ `['send_dga', 'is_error', 'date_time_medition']` |
| 10 | Throttling API Ikolu | `api_ik/views.py` | ✅ Todos los endpoints tienen rate limiting |
| 11 | Tests Ikolu | `tests/` | ✅ 10 tests nuevos |

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
| 16 | Mover credenciales TDATA a variables de entorno | Eliminar hardcodeo |

---

## 4. Estado del Subsistema de Alertas

### Reglas activas en producción

| Regla | Target Type | Canal | Estado |
|-------|-------------|-------|--------|
| Desconexión | `DISCONNECTION` | Google Chat + IA | ✅ Activo |
| Reconexión | `RECONNECTION` | Google Chat | ✅ Activo |
| Error de procesamiento | `PROCESSING_ERROR` | Google Chat | ✅ Activo |
| Umbral caudal máximo | `THRESHOLD_MAX` | Email / Google Chat | ✅ Activo |
| Umbral caudal mínimo | `THRESHOLD_MIN` | Email / Google Chat | ✅ Activo |
| Sin datos | `NO_DATA` | Email / Google Chat | ✅ Activo |
| Tasa de cambio | `RATE_OF_CHANGE` | Email / Google Chat | 🟡 Disponible |
| Desviación estadística | `DEVIATION` | Email / Google Chat | 🟡 Disponible |
| Reporte programado | `SCHEDULED_REPORT` | Email / Google Chat | 🟡 Disponible |

**Legacy desactivado:**
- `check_and_notify_disconnection` ❌ Reemplazado por AlertRule
- `check_and_notify_reconnection` ❌ Reemplazado por AlertRule
- `check_and_notify_error` ❌ Reemplazado por AlertRule

---

## 5. Estado de Tests

| Suite | Tests | Estado |
|-------|-------|--------|
| `tests.regression` | 115 | ✅ Todos pasando |
| `tests.dga` | 5 | ✅ Todos pasando |
| `tests.baseline` | — | ⏳ Pendiente revisión |
| **Total** | **120** | **✅ Todos pasando** |

**Fixes aplicados a tests (2026):**
- `CatchmentPoint` ahora requiere `owner_user` y `project` (NOT NULL) — tests actualizados
- `DgaDataConfigCatchment` se crea automáticamente por signal — tests ajustados para modificar en vez de crear duplicados
- `@patch('api.cronjobs.dga.cron_dga.settings')` → `@override_settings()` (settings no importado a nivel módulo)
- Test FPC Tissue actualizado: bloqueo removido de producción, valida comportamiento actual
- 10 tests Ikolu nuevos cubriendo endpoints críticos del Centro de Control

---

## 6. Próximos Pasos Recomendados

1. **Corregir CORS en producción** — Remover `localhost` de `CORS_ALLOWED_ORIGINS`
2. **Mover credenciales TDATA a variables de entorno** — Eliminar hardcodeo de `getters/tdata.py`
3. **Agregar `db_index=True` a FKs frecuentes** restantes — Requiere migración en horario de baja
4. **Cachear `PointsSummaryView`** con Redis — Reduce carga en pantalla principal de app
5. **Evaluar WebSocket** para telemetría en tiempo real — Reduce polling del dashboard
