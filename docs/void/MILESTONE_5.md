# Milestone 5 — Compliance REST API + Pipeline→Compliance + Motor de alertas

> Estado: **cerrado** — API REST de cumplimiento, conexión pipeline→compliance bajo feature flag, y motor de alertas con canales configurables.  
> Fecha cierre: 2026-07-06  
> Objetivo: completar la operación de compliance y alertas en `void` sin tocar legacy.

---

## 1. Contexto

El **Milestone 4** cerró con la API REST base y autenticación JWT.  
El **Milestone 5** agrega:

- Gestión de entidades regulatorias, estándares y perfiles de cumplimiento vía API REST.
- Envío automático de lecturas procesadas a compliance solo cuando `VOID_AUTOMATION_ENABLED=True`.
- Motor de alertas reactivo basado en `DeviceEvent`, reglas configurables y dispatch asíncrono.

Todo permanece desacoplado del sistema legacy; `VOID_AUTOMATION_ENABLED=False` por defecto en producción.

---

## 2. Entregables

| Entregable | Estado |
|---|---|
| API REST de compliance: authorities, standards, profiles | ✅ |
| Serializadores nested con write-only IDs | ✅ |
| Permisos por punto en perfiles de compliance | ✅ |
| Pipeline → `ComplianceService.submit_reading` bajo flag | ✅ |
| Modelos `AlertRule` y `AlertTrigger` | ✅ |
| `AlertEngine` con filtros y cooldown | ✅ |
| `AlertDispatcher` con canales email/SMS/webhook/push/in-app | ✅ |
| Señal `post_save` en `DeviceEvent` | ✅ |
| Tarea Celery `void_dispatch_alerts` | ✅ |
| Tests de void | ✅ 127/127 OK |
| Tests de regresión + DGA | ✅ 294/294 OK |
| Documentación actualizada | ✅ |

---

## 3. Modelo de datos

```
ComplianceAuthority (DGA, SMA, etc.)
├── PointComplianceProfile → Point
│   ├── ComplianceStandard (schedule de envío)
│   └── ComplianceSubmission (trazabilidad)
│
DeviceEvent (reset, salto, offline, etc.)
├── AlertRule (filtros + canales + cooldown)
│   └── AlertTrigger (instancia a enviar)
```

---

## 4. API

### Compliance

| Endpoint | Descripción |
|---|---|
| `GET/POST /void/compliance/authorities/` | CRUD entidades regulatorias |
| `GET/POST /void/compliance/standards/` | CRUD estándares de envío |
| `GET/POST /void/compliance/profiles/` | CRUD perfiles por punto |
| `POST /void/compliance/submit/` | Envío manual staff |
| `GET /void/compliance/submissions/` | Listado de submissions |
| `GET /void/compliance/queue/` | Resumen de cola pendiente |

### Alertas

Las alertas se configuran en el admin / futura API:

- `AlertRule`: filtros por event_type, severity, device, point, variable; cooldown; canales; destinatarios; plantilla.
- `AlertTrigger`: creado automáticamente al generarse un `DeviceEvent` que califique.

Tarea Celery para dispatch batch:

```python
void_dispatch_alerts.delay()
# o por IDs específicos
void_dispatch_alerts.delay(trigger_ids=[1, 2])
```

---

## 5. Feature flags

| Flag | Default | Efecto |
|---|---|---|
| `VOID_AUTOMATION_ENABLED` | `False` | Activa pipeline automático, ingesta Celery y envío a compliance. |

Cuando está desactivado (producción actual):

- El pipeline procesa lecturas normalmente.
- No se envía automáticamente a compliance.
- Las alertas siguen evaluándose al crear `DeviceEvent`, pero los dispatch son tasks async que pueden quedar en cola.

---

## 6. Pipeline → Compliance

En `void/services/pipeline.py`:

```python
if _AutomationFlags.pipeline_triggers_compliance() and not processed.is_error:
    self._submit_to_compliance(processed)
```

El import de `ComplianceService` es lazy para evitar circularidad con `void.services`.

---

## 7. Motor de alertas

### Flujo

1. `DeviceEvent` se crea (desde handler stateful u otro origen).
2. Señal `post_save` llama a `AlertEngine.evaluate_event(event)`.
3. Se generan `AlertTrigger` para cada `AlertRule` que matchee y pase cooldown.
4. Se encola `void_dispatch_alerts.delay(trigger_ids=[...])`.
5. Celery usa `AlertDispatcher.dispatch(trigger)` para enviar por cada canal.

### Canales soportados

| Canal | Estado |
|---|---|
| `email` | Implementado vía `django.core.mail.send_mail` |
| `sms` | Placeholder (integrar con proveedor) |
| `webhook` | Placeholder |
| `push` | Placeholder |
| `in_app` | Marcado como enviado (base para notificaciones internas) |

---

## 8. Migraciones

- `0027_alertrule_alerttrigger`: crea `AlertRule` y `AlertTrigger`.

---

## 9. Tests

```bash
# Void
python manage.py test void.tests --noinput --keepdb
# Resultado: 127 tests OK

# Regresión + DGA
python manage.py test tests.regression tests.dga --noinput --keepdb
# Resultado: 294 tests OK
```

Nuevos tests:

- `void/tests/test_api_compliance.py`: CRUD de authorities/standards/profiles vía API.
- `void/tests/test_alerts.py`: motor de alertas, dispatcher y señal.

---

## 10. Qué NO incluye este milestone

- Throttling específico de void.
- Schema OpenAPI separado para `/void/`.
- Backfill real masivo.
- Envío agregado de compliance por período (`submit_period` es placeholder).
- Canales SMS/webhook/push implementados con proveedores reales.

---

## 11. Próximos pasos recomendados (Milestone 6)

1. API REST de alertas (`/void/alerts/rules/`, `/void/alerts/triggers/`).
2. Throttling y rate limiting en endpoints void.
3. Reportes async (JSON/XLSX) de lecturas.
4. Backfill masivo desde providers hacia `void`.
5. Implementar SMS/webhook reales.
