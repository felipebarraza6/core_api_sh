# Setup de Celery en SmartHydro

> **Estado:** FASE 1.1 completada. Celery está configurado y validado, pero **no reemplaza a django-crontab todavía**.

---

## ¿Qué se agregó?

- `api/celery.py` — configuración de Celery con Redis como broker y backend.
- `api/__init__.py` — autodiscover de tareas.
- `api/core/tasks/health_tasks.py` — tarea de prueba `ping_celery`.
- `api/core/views/health.py` — endpoint `GET /health/celery/`.
- `api/urls.py` — ruta `/health/celery/`.
- `docker-compose.celery.yml` — servicios `celery_worker` y `celery_beat` para dev/staging.
- `tests/regression/test_celery_health.py` — tests de regresión del health check.

---

## Variables de entorno

Celery reutiliza las mismas variables de Redis:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `REDIS_HOST` | `redis_secure` | Host del broker Redis |
| `REDIS_PORT` | `6379` | Puerto Redis |
| `REDIS_PASSWORD` | — | Contraseña (obligatoria en prod) |
| `REDIS_DB_BROKER` | `0` | DB para broker |
| `REDIS_DB_BACKEND` | `1` | DB para result backend |

---

## Levantar Celery en dev/staging

```bash
# Desde la raíz del proyecto
docker compose -f docker-compose.production.secure.yml -f docker-compose.celery.yml up -d --build celery_worker celery_beat
```

> Nota: `docker-compose.celery.yml` reutiliza la imagen del servicio `django`. Debes reconstruirla (`--build`) para que `celery` esté instalado desde `requirements.txt`.

---

## Verificar funcionamiento

```bash
# Health check básico
curl -s https://api.smarthydro.app/health/

# Health check de Celery (requiere worker corriendo)
curl -s -L https://api.smarthydro.app/health/celery/
```

Respuesta esperada:

```json
{
  "status": "ok",
  "celery": "ok",
  "task_id": "...",
  "result": true,
  "timestamp": "..."
}
```

---

## Ejecutar tarea manualmente

```bash
docker exec django_api_secure celery -A api call api.core.tasks.health_tasks.ping_celery
```

---

## Monitorear workers

```bash
# Listar workers activos
docker exec django_api_secure celery -A api inspect active

# Ping a todos los workers
docker exec django_api_secure celery -A api inspect ping
```

---

## Próximos pasos (FASE 1.2+)

1. Migrar cronjobs de `django-crontab` a tasks Celery uno a uno.
2. Agregar feature flags para activar/desactivar cada tarea en Celery vs crontab.
3. Implementar `django-celery-beat` para scheduling persistente (agregar a `requirements.txt` y correr migraciones cuando se use).
4. Monitorear colas y reintentos con Flower (opcional).

---

## Seguridad

- Redis requiere autenticación (`REDIS_PASSWORD`).
- El backend de resultados usa DB `1` separada del broker DB `0`.
- Los workers corren con el mismo usuario no-root (`1000:1000`) que el servicio Django.
