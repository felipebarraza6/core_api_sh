# Mapa de Duplicación Legacy ↔ Ikolu

> **Objetivo:** identificar qué recursos están implementados tanto en `/api/` (legacy, DefaultRouter) como en `/api/ik/` (Ikolu, APIViews optimizadas), para decidir dónde debe vivir la fuente de verdad y qué legacy se deprecará.

---

## Leyenda

| Símbolo | Significado |
|---------|-------------|
| ✅ | Disponible en ambas APIs (duplicación confirmada) |
| ⚠️ | Disponible en legacy, con equivalente parcial o indirecto en Ikolu |
| ❌ | Solo en legacy (sin equivalente Ikolu) |
| 🆕 | Solo en Ikolu (funcionalidad nueva) |
| 🔴 | Crítico: no tocar sin análisis previo |

---

## 1. Autenticación y usuarios

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| Login | `POST /api/users/login/` | `POST /api/ik/login/` | ✅ Duplicado. Ikolu devuelve resumen liviano. Fuente de verdad: servicio de autenticación compartido. |
| Signup | `POST /api/users/signup/` | — | ❌ Solo legacy. Debe conservarse o migrarse a `/api/ik/auth/signup/`. |
| Me / perfil | `GET /api/users/me/` | — | ❌ Solo legacy. Ikolu lo incluye en login. |
| Cambio de password | `POST /api/users/change-password/` | — | ❌ Solo legacy. |
| Password reset | `POST /api/password_reset/` | `POST /api/ik/auth/password-reset/` | ✅ Duplicado (misma librería `django_rest_passwordreset`). |
| Listado de staff | — | `GET /api/ik/staff_users/` | 🆕 Necesario para asignación de tickets. |

**Recomendación:** extraer `UserService` que maneje login, signup, cambio de password y perfil. Mantener endpoints legacy como proxies a `/api/ik/` de forma transparente.

---

## 2. Clientes y proyectos

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| Cliente CRUD | `ClientViewSet` (`/api/client/`) | — | ❌ Solo legacy. Ikolu no expone CRUD de clientes. |
| Clientes con proyectos | `GET /api/client/with-projects/` | — | ❌ Solo legacy. |
| Proyectos CRUD | `ProjectCatchmentsViewSet` (`/api/project_catchments/`) | — | ❌ Solo legacy. |
| Puntos por proyecto | Anidado en `CatchmentPointViewSet` | `GET /api/ik/points_summary/` | ⚠️ Parcial. Legacy permite CRUD; Ikolu solo resumen/lectura. |

**Recomendación:** crear `ClientService` y `ProjectService`. Exponer CRUD tanto en legacy como en Ikolu. Legacy actuará como proxy.

---

## 3. Puntos de captación (CatchmentPoint)

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| CRUD de puntos | `CatchmentPointViewSet` | — | ❌ Solo legacy. Ikolu consume datos pero no edita. |
| Resumen de puntos | `GET /api/catchment_point/all/` | `GET /api/ik/points_summary/` | ✅ Duplicado. Ikolu es más eficiente. |
| Resumen de un punto | `GET /api/catchment_point/<id>/` | `GET /api/ik/point/<id>/summary/` | ✅ Duplicado. |
| Mis puntos (dropdown) | — | `GET /api/ik/my_points/` | 🆕 Liviano, solo Ikolu. |
| Config del punto | `ProfileDataConfigCatchmentViewSet` | `GET/POST /api/ik/point/<id>/config/` | ✅ Duplicado. Fuente de verdad: `PointConfigService`. |
| Variables del punto | `VariableViewSet` | `GET /api/ik/point/<id>/variables/` | ✅ Duplicado. |
| Esquemas | `SchemesCatchmentViewSet` | Incluido en `point_summary` | ⚠️ Parcial. |
| Perfiles Ikolu | `ProfileIkoluCatchmentViewSet` | Incluido en `point_summary` | ⚠️ Parcial. Será reemplazado por suscripciones. |

**Recomendación:** centralizar en `PointService` y `PointConfigService`. Legacy delega a servicios.

---

## 4. Telemetría

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| Registros por rango | `InteractionDetailViewSet` | `GET /api/ik/point/<id>/records/` | ✅ Duplicado. Ikolu devuelve campos esenciales. |
| Batch telemetry | — | `POST /api/ik/batch/telemetry/` | 🆕 Ikolu. Optimizado para móvil/frontend. |
| Batch stats | — | `POST /api/ik/batch/stats/` | 🆕 Ikolu. |
| Calendario | — | `GET /api/ik/point/<id>/calendar/` | 🆕 Ikolu. |
| Gaps | — | `GET /api/ik/point/<id>/gaps/` | 🆕 Ikolu. |
| Override de registros | `InteractionDetailOverrideViewSet` | — | ❌ Solo legacy (staff). |
| Override mensual | `InteractionDetailOverrideMonthViewSet` | — | ❌ Solo legacy (staff). |
| XLS/XLSX | `InteractionXLS`, `InteractionXLSMonth`, `InteractionXLSDga` | — | ❌ Solo legacy. |
| Reprocessor | `POST /api/telemetry-reprocessor/` | — | ❌ Solo legacy (staff). Debería exponerse también en Ikolu admin. |
| Backfill histórico | — | `POST /api/ik/telemetry/backfill/` | 🆕 Ikolu. |

**Recomendación:** crear `TelemetryService` unificado. Todos los endpoints deben delegar en él. Legacy mantiene contratos antiguos; Ikolu contratos nuevos.

---

## 5. Compliance DGA / SMA

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| Config DGA | `DgaDataConfigCatchmentViewSet` | Incluido en `point_config` | ⚠️ Parcial. |
| Listado compliance | — | `GET /api/ik/compliance/` | 🆕 Ikolu. |
| Toggle compliance | `ManagementViewSet` (`toggle_compliance`) | `POST /api/ik/management/toggle_compliance/` | ✅ Duplicado. |
| Historial de caudal | — | `GET /api/ik/compliance/<id>/flow_history/` | 🆕 Ikolu. |
| Near limit | — | `GET /api/ik/compliance/<id>/near_limit/` | 🆕 Ikolu. |
| Verificación DGA (pública) | `POST /compliance/dga/verify/` | — | ❌ Solo legacy. |

**Recomendación:** `ComplianceService` compartido. Legacy y Ikolu usan el mismo servicio.

---

## 6. Alertas y eventos de sistema

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| Reglas de alerta | `AlertRuleViewSet` | — | ❌ Solo legacy. |
| Canales de alerta | `AlertChannelViewSet` | — | ❌ Solo legacy. |
| Triggers | `AlertTriggerViewSet` | — | ❌ Solo legacy. |
| Eventos de sistema | `SystemEventViewSet` | `GET /api/ik/system-events/summary/` | ⚠️ Parcial. Legacy CRUD; Ikolu resumen. |

**Recomendación:** `AlertService` y `SystemEventService`. Legacy CRUD; Ikolu resumen.

---

## 7. Reportes y management

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| Reportes | `ReportsGenerationViewSet` | — | ❌ Solo legacy. |
| Puntos activos | `GET /reports/active-points/` | — | ❌ Solo legacy. |
| Management | `ManagementViewSet` | — | ❌ Solo legacy (pero algunas acciones están en Ikolu compliance). |
| Dashboard stats | — | `GET /api/ik/dashboard_stats/` | 🆕 Ikolu. |
| Control center | — | `/api/ik/control_center/*` | 🆕 Ikolu. |

---

## 8. Tickets de soporte + SLA

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| Tickets CRUD | — | `/api/ik/tickets/*` | 🆕 Subsistema nuevo, solo Ikolu. |
| Categorías | — | `/api/ik/ticket-categories/*` | 🆕 Solo Ikolu. |
| SLA | — | `/api/ik/sla-configs/*` | 🆕 Solo Ikolu. |

**Recomendación:** el subsistema de tickets ya es Ikolu-first. No hay legacy que deprecar aquí.

---

## 9. Chatbot / Agents

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| Chatbot legacy | `POST /api/chat/` | — | ❌ Solo legacy. Código actual en `api.core.chatbot`. |
| Chat interpretativo | — | `POST /api/ik/chat/client/general_stats/` | 🆕 Solo Ikolu. |

**Recomendación:** a futuro reemplazar chatbot legacy por sistema de agents configurable (FASE 6).

---

## 10. Archivos, notificaciones y otros

| Recurso | Legacy `/api/` | Ikolu `/api/ik/` | Notas / Fuente de verdad propuesta |
|---------|---------------|------------------|------------------------------------|
| Notificaciones | `NotificationsCatchmentViewSet` | — | ❌ Solo legacy. Será reemplazado por alertas + tickets. |
| Respuestas a notificaciones | `ResponseNotificationsCatchmentViewSet` | — | ❌ Solo legacy. |
| Tipos de archivo | `TypeFileCatchmentViewSet` | — | ❌ Solo legacy. |
| Archivos | `FileCatchmentViewSet` | — | ❌ Solo legacy. |
| Register persons | `RegisterPersonsViewSet` | — | ❌ Solo legacy. |
| Counter reset logs | `CounterResetLogViewSet` | — | ❌ Solo legacy. |
| Telemetry providers | `TelemetryProviderViewSet` | — | ❌ Solo legacy. |
| Compliance providers | `ComplianceProviderViewSet` | — | ❌ Solo legacy. |

---

## Conclusiones del mapa

1. **Mayor duplicación en:** autenticación, puntos de captación, telemetría, compliance.
2. **Legacy sin equivalente Ikolu (a mantener/proxy):** CRUD de clientes/proyectos/puntos, reportes, alertas, archivos, notificaciones, reprocessor.
3. **Ikolu sin equivalente legacy (a expandir):** tickets, control center, dashboard, batch endpoints, agents.
4. **Próximos servicios a extraer (orden de prioridad):**
   1. `AuthenticationService` (login/signup/password)
   2. `PointService` (resumen, listado, config)
   3. `TelemetryService` (registros, batch, calendario)
   4. `ComplianceService` (toggle, historial, near limit)
   5. `AlertService` / `SystemEventService`

---

> **Nota:** este mapa es una foto estática. La fuente de verdad debe moverse a servicios; los endpoints legacy se convertirán en proxies delgados que conservan el contrato de respuesta histórico.
