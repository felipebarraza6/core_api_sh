# Milestone 6 — API REST de alertas

> Estado: **cerrado** — CRUD de reglas de alerta y consulta/dispatch de triggers vía API REST.  
> Fecha cierre: 2026-07-06  
> Objetivo: permitir gestionar alertas desde el front nuevo sin tocar legacy.

---

## 1. Contexto

El **Milestone 5** cerró con el motor de alertas reactivo (`AlertRule`, `AlertTrigger`, dispatch vía Celery).  
El **Milestone 6** expone ese motor a través de la API REST para que operadores puedan:

- Crear, editar y desactivar reglas de alerta.
- Ver triggers generados.
- Forzar el reenvío de un trigger pendiente.

---

## 2. Entregables

| Entregable | Estado |
|---|---|
| `AlertRuleSerializer` | ✅ |
| `AlertTriggerSerializer` (read-only) | ✅ |
| `AlertRuleViewSet` (CRUD) | ✅ |
| `AlertTriggerViewSet` (list/detail + acción dispatch) | ✅ |
| Endpoints `/void/alerts/rules/` y `/void/alerts/triggers/` | ✅ |
| Acción `POST /void/alerts/triggers/<id>/dispatch_now/` | ✅ |
| Tests de void | ✅ 134/134 OK |
| Documentación actualizada | ✅ |

---

## 3. API

### Reglas de alerta

| Endpoint | Método | Descripción |
|---|---|---|
| `/void/alerts/rules/` | GET | Listar reglas |
| `/void/alerts/rules/` | POST | Crear regla |
| `/void/alerts/rules/<id>/` | GET/PUT/PATCH/DELETE | CRUD individual |

Payload ejemplo:

```json
{
  "name": "Reset crítico",
  "is_active": true,
  "event_types": ["counter_reset"],
  "severities": ["critical"],
  "device_ids": [],
  "point_ids": [],
  "variables": ["pulses"],
  "cooldown_minutes": 60,
  "channels": ["email", "in_app"],
  "recipients": {
    "emails": ["ops@smarthydro.cl"]
  },
  "message_template": "[{severity}] {event_type} en {device}: {message}"
}
```

### Triggers

| Endpoint | Método | Descripción |
|---|---|---|
| `/void/alerts/triggers/` | GET | Listar triggers |
| `/void/alerts/triggers/<id>/` | GET | Detalle |
| `/void/alerts/triggers/<id>/dispatch_now/` | POST | Forzar envío de trigger pendiente |

Los triggers son **solo lectura**: no se crean ni editan por API; se generan automáticamente al crear un `DeviceEvent` que califique.

---

## 4. Permisos

- `admin` / `operator`: acceso total.
- `client_admin` / `viewer`: heredan `VoidRolePermission` (actualmente solo lectura para viewer; client_admin también lectura).  
  *Nota:* si se requiere que client_admin edite reglas, se debe ajustar `VoidRolePermission` o crear permiso específico.

---

## 5. Tests

```bash
python manage.py test void.tests --noinput --keepdb
# Resultado: 134 tests OK
```

Nuevo test: `void/tests/test_api_alerts.py`.

---

## 6. Qué NO incluye este milestone

- Canales SMS/webhook/push con proveedores reales.
- Suscripciones de usuarios a reglas.
- Alertas por umbral de variables (requiere lógica de telemetría madura).
- Notificaciones in-app persistentes con badge/unread count.

---

## 7. Próximos pasos recomendados (Milestone 7)

1. Replicar lógica crítica de `controllers/total.py` en `PipelineService` (monotonicidad, resets, reconexiones, caudal).
2. Implementar canal webhook real (configurable por regla).
3. Agregar alertas por umbral sobre `ProcessedReading`.
