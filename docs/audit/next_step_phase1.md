# Próximo paso concreto — FASE 1: Infraestructura no invasiva

> **Contexto:** FASE 0 completada (auditoría y baseline). Se identificó que:
> - Los endpoints legacy **sí tienen tráfico real**; no se puede deprecar `/api/` de golpe.
> - Los tests de regresión + DGA pasan dentro del contenedor Django+PostgreSQL, pero tardan varios minutos.
> - `api/settings_test.py` (SQLite) está roto por SQL específico de PostgreSQL en migración `0059`.
> - No hay capa de servicios compartidos; legacy e Ikolu duplican lógica.

## Propuesta: introducir Celery de forma segura (no reemplaza crontab todavía)

En lugar de saltar directamente a migrar cronjobs o reestructurar modelos, el siguiente paso más seguro y valioso es **preparar el terreno con Celery** sin afectar el procesamiento actual.

### Por qué Celery primero

1. **No toca modelos ni endpoints.** Solo agrega configuración y un par de tareas de prueba.
2. **Permite luego migrar cronjobs uno a uno** con feature flags, sin apagones.
3. **Habilita el patrón de servicios asíncronos** que necesitarán CRM, suscripciones y agents.
4. **Redis ya está corriendo** en producción; no hace falta agregar infraestructura nueva.

### Cambios concretos (FASE 1.1)

| # | Archivo/acción | Descripción |
|---|----------------|-------------|
| 1 | `requirements.txt` | Agregar `celery>=5.3,<6.0` y `redis>=5.0` (si no están). |
| 2 | `api/celery.py` | Configurar app Celery con broker/backend Redis, usando `REDIS_PASSWORD`. |
| 3 | `api/__init__.py` | Hacer `from .celery import app as celery_app` para autodiscover. |
| 4 | `api/core/tasks/__init__.py` | App tasks inicial. |
| 5 | `api/core/tasks/health_tasks.py` | Tarea `ping_celery()` que devuelve `pong` y escribe en log. |
| 6 | `api/core/views/health.py` | Agregar endpoint `GET /health/celery/` que encola `ping_celery()` y verifica respuesta. |
| 7 | `docker-compose.celery.yml` | Nuevo archivo con servicios `celery_worker` y `celery_beat` para dev/staging. |
| 8 | `docs/CELERY_SETUP.md` | Guía para levantar workers en dev y monitorear en producción. |
| 9 | Tests | Agregar `tests/regression/test_celery_health.py` que verifique que Celery responde. |

### Qué NO se toca

- `CRONJOBS` en `settings.py` se mantiene intacto.
- `api/cronjobs/telemetry/*` no se modifica.
- Ningún endpoint existente cambia de contrato.
- No se agregan migraciones.

### Criterios de aceptación

- [ ] `docker compose -f docker-compose.celery.yml up celery_worker celery_beat` levanta sin errores en dev.
- [ ] `GET /health/celery/` responde `{"celery": "ok", "task_id": "...", "result": "pong"}`.
- [ ] `python manage.py test tests.regression tests.dga --noinput --keepdb` sigue pasando (sin regresión).
- [ ] No hay credenciales hardcodeadas en la configuración de Celery.

### Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Celery consume recursos | Limitar workers a 1 en dev, 2 en prod; memory limit en Docker. |
| Redis no autenticado | Usar `REDIS_PASSWORD` ya configurado. |
| Conflicto con crontab | Celery corre en servicios separados; crontab legacy sigue siendo la fuente de verdad hasta FASE 1.3. |

---

## Alternativa: arreglar tests en SQLite primero

Si el objetivo inmediato es mejorar la velocidad de feedback para developers, el próximo paso podría ser:

1. Crear un settings de test basado en PostgreSQL (`settings_test_pg.py`) que use la misma DB del contenedor pero una base `test_smarthydro_prod` y `--keepdb`.
2. O, modificar `settings_test.py` para interceptar la migración `0059` y ejecutar SQL compatible con SQLite solo en tests.

**Recomendación:** hacer ambas cosas en paralelo, pero priorizar Celery porque desbloquea la arquitectura futura.

---

## Decisiones pendientes

1. ¿Versión de Django a la que apuntamos primero: **5.2 LTS** o **6.x**? (5.2 LTS es más conservador; 6.x alinea con Yggdra.)
2. ¿Nombre de la app para CRM/suscripciones: `api.crm`, `api.subscriptions`, o dentro de `api.core`? (Recomendación: apps separadas para alinear con Yggdra.)
3. ¿Feature flag framework: variable de entorno simple o librería como `django-waffle`? (Recomendación: variable de entorno simple por ahora.)
