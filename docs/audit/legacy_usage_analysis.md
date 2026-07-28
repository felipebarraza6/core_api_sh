# Análisis de Uso de Endpoints Legacy (últimos 7 días)

> **Fuente:** logs de `django_api_secure` filtrados por rutas `/api/`.
> **Período:** 2026-06-27 a 2026-07-04 (7 días).
> **Metodología:** conteo de líneas de log con método HTTP + ruta. Se eliminaron query strings para agrupar.

---

## Resumen ejecutivo

- **Endpoints con tráfico real (legacy + ikolu):** ~80 rutas distintas.
- **Legacy más usados:** `interaction_detail_json`, `users/login`, `client/with-projects`, `catchment_point/all`, `users/`.
- **Ikolu más usados:** `tickets`, `compliance`, `control_center/*`, `ticket-categories`, `staff_users`.
- **Conclusión:** muchos endpoints legacy **sí tienen tráfico**. No se puede deprecar `/api/` a ciegas; hay que hacerlo endpoint por endpoint con proxies.

---

## Top de endpoints legacy con tráfico real

| # | Endpoint | Métodos observados | Hits 7d | Impacto si se elimina |
|---|----------|-------------------|---------|----------------------|
| 1 | `/api/interaction_detail_json/` | GET | 1574 | **Crítico.** Usado por múltiples puntos (125, 128, 146, 78, 117, etc.). Requiere equivalente Ikolu estable. |
| 2 | `/api/users/login/` | POST | 737 | **Crítico.** Login principal de usuarios legacy. |
| 3 | `/api/client/with-projects/` | GET | 544 | **Crítico.** Usado para carga inicial de clientes/proyectos. |
| 4 | `/api/catchment_point/all/` | GET | 331 | **Crítico.** Listado de puntos. Equivalente parcial en Ikolu (`points_summary`, `my_points`). |
| 5 | `/api/users/` | GET | 132 | **Crítico.** Listado de usuarios para admin/asignación. |
| 6 | `/api/notifications_catchment/` | GET | 38 | **Medio.** Sistema de notificaciones legacy. |
| 7 | `/api/alert_rules/` | GET | 28 | **Medio.** Configuración de alertas. |
| 8 | `/api/client/` | GET | 26 | **Medio.** CRUD cliente. |
| 9 | `/api/project_catchments/` | GET | 23 | **Medio.** CRUD proyectos. |
| 10 | `/api/response_notifications_catchment/` | GET | 16 | **Medio.** Respuestas a notificaciones. |
| 11 | `/api/telemetry_providers/` | GET | 18 | **Medio.** Catálogo de providers. |
| 12 | `/api/schemes_catchment/` | GET | 17 | **Medio.** Esquemas de puntos. |
| 13 | `/api/client/all/` | GET | 17 | **Medio.** Listado simple de clientes. |
| 14 | `/api/alert_channels/` | GET | 15 | **Medio.** Canales de alerta. |
| 15 | `/api/alert_triggers/` | GET | 14 | **Medio.** Triggers de alertas. |
| 16 | `/api/variable/` | GET | 13 | **Medio.** Variables de puntos. |
| 17 | `/api/management/resources_status/` | GET | 13 | **Medio.** Recursos del sistema. |
| 18 | `/api/interaction_detail_override_month/` | GET | 10 | **Bajo.** Uso administrativo. |
| 19 | `/api/interaction_detail/` | GET | 8 | **Bajo.** XLS/listado. |
| 20 | `/api/compliance_providers/` | GET | 8 | **Bajo.** Providers de compliance. |
| 21 | `/api/interaction_detail_dga/` | GET | 6 | **Bajo.** Reporte DGA. |
| 22 | `/api/management/telemetry_metrics/` | GET | 6 | **Bajo.** Métricas de telemetría. |
| 23 | `/api/management/points_status/` | GET | 6 | **Bajo.** Estado de puntos. |
| 24 | `/api/project_catchments/all/` | GET | 11 | **Bajo.** Listado simple de proyectos. |
| 25 | `/api/telemetry-reprocessor/` | POST | 31 | **Medio/Alto (staff).** Usado para reparar datos. |

---

## Endpoints legacy sin tráfico detectado (últimos 7 días)

Los siguientes endpoints no aparecieron en los logs analizados. **Esto no significa que estén muertos:** pueden usarse mensualmente, en batch, o desde otros servicios. Requieren confirmación antes de deprecar.

- `/api/interaction_detail_override/`
- `/api/counter_reset_logs/`
- `/api/dga_data_config_catchment/`
- `/api/file_catchment/`
- `/api/type_file_catchment/`
- `/api/profile_data_config_catchment/`
- `/api/profile_ikolu_catchment/`
- `/api/register_persons/`
- `/api/reports/`
- `/api/system_events/`
- `/api/users/signup/`
- `/api/users/me/`
- `/api/users/change-password/`
- `/api/management/` (acciones específicas)

> **Nota:** endpoints como `file_catchment`, `profile_data_config_catchment`, `dga_data_config_catchment` probablemente se acceden vía admin de Django o mediante IDs específicos; el conteo por ruta base puede subestimar su uso.

---

## Patrones detectados

1. **`/api/interaction_detail_json/?catchment_point=X&hour=0` es el endpoint legacy más usado.** Muestra últimos datos de telemetría por punto. Es candidato prioritario a migrar a `/api/ik/point/<id>/records/` o `/api/ik/point/<id>/summary/`.
2. **`/api/client/with-projects/` y `/api/catchment_point/all/` son el corazón del frontend legacy.** Cualquier deprecación debe empezar por crear equivalentes Ikolu con mismo contrato o proxy transparente.
3. **`/api/users/login/` sigue siendo el login principal.** Aunque existe `/api/ik/login/`, la mayoría de usuarios usa el legacy.
4. **Ikolu es dominante en tickets y control center.** Confirmado: el frontend moderno ya está en Ikolu.
5. **Alertas (`alert_rules`, `alert_channels`, `alert_triggers`) y notificaciones legacy siguen activas.** Son dependencias directas de operaciones.

---

## Recomendaciones inmediatas (sin romper nada)

1. **No eliminar `/api/` globalmente.** Deprecar endpoint a endpoint.
2. **Crear proxies de legacy a servicios compartidos** para los endpoints más usados:
   - `interaction_detail_json` → `TelemetryService`
   - `client/with-projects` → `ClientService` + `ProjectService`
   - `catchment_point/all` → `PointService`
   - `users/login` → `AuthenticationService`
3. **Mantener contratos de respuesta** de estos endpoints legacy exactamente iguales.
4. **Monitorear 30 días más** antes de marcar como "sin uso" los endpoints de la lista de arriba.
5. **Ikolu ya es la API preferida** para tickets, control center, compliance y dashboard. Invertir allí para nuevas funcionalidades.
