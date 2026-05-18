# AGENTS.md — API Backend

> **Auditoría:** 2026-05-14 | **Estado:** Producción activa

## ⚠️ Zonas de Alto Riesgo

### Models (`api/core/models/`)
- `catchment_points.py` (~19KB) contiene la mayoría de los modelos.
- **Hallazgo crítico:** `DecimalField(max_length=1200)` en línea ~475 — `DecimalField` no tiene `max_length`, usa `max_digits` + `decimal_places`.
- **Hallazgo crítico:** `IntegerField(default=0.0)` — default float en campo entero.
- **Hallazgo alto:** Ningún campo FK tiene `db_index=True`. Filtros frecuentes:
  - `CatchmentPoint.project`, `owner_user`
  - `NotificationsCatchment.point_catchment`
  - `ProfileDataConfigCatchment.point_catchment`
  - `DgaDataConfigCatchment.point_catchment`
  - `FileCatchment.point_catchment`
  - `ResponseNotificationsCatchment.notification`, `user`

### Views (`api/core/views/`)
- **N+1 severo:** `management.py:points_status` — dentro de un loop hace:
  - `InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition').first()`
  - `ProfileDataConfigCatchment.objects.filter(point_catchment=point, is_telemetry=True).exists()`
  - Con 500 puntos → 1000+ queries adicionales.
- **Sin paginación:** `ClientViewSet`, `ProjectCatchmentsViewSet`, `CatchmentPointViewSet` usan `.all()` sin límite.

### Serializers (`api/core/serializers/`)
- Variantes complejas de `InteractionDetail` para XLS, JSON, override.
- Si se agrega un campo nuevo, asegurar que sea opcional o tenga default.

### Signals (`api/core/signals/`)
- `notifications.py`: Crea notificaciones al cambiar datos. Cuidado con loops.
- Se cargan en `apps.py` vía `ready()`.

### Admin (`api/core/admin.py`)
- Usa `django-unfold`.
- Modelos registrados con clases de unfold.

### Migrations
- Nunca editar migraciones existentes.
- Migraciones 0026-0030 son recientes; verificar estado en producción con `showmigrations`.

## 🔴 Código Crítico — No modificar sin plan

| Archivo | Por qué es crítico |
|---------|-------------------|
| `cronjobs/telemetry/controllers/total.py` | Unificación de pulsos. Race condition conocida en línea 160-162. |
| `cronjobs/telemetry/getters/tdata.py` | Credenciales TDATA hardcodeadas (líneas 12-13). |
| `core/signals/notifications.py` | Dispara alertas a clientes. |
| `core/models/catchment_points.py` | Dominio completo. Cambios = migraciones + riesgo de datos. |

## 🧪 Tests

```bash
# Regresión — DEBEN pasar siempre
python manage.py test tests.regression

# DGA
python manage.py test tests.dga
```

## 📝 Comandos Management

- `recalc_totals.py`: Recalcula totales de telemetría. Muy pesado.
- Heredar de `BaseCommand` y usar `self.stdout.write()` para logs.

## 📦 Dependencias

- Archivo: `api/requirements.txt`
- Django: `>=4.2.0,<5.0.0`
- Python del Dockerfile: 3.11
