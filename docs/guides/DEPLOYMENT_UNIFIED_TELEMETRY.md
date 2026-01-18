# 🚀 GUÍA DE DEPLOYMENT - Sistema Unificado de Telemetría V3.1

**Versión**: V3.1
**Fecha**: 2026-01-17
**Sistema**: Celery + Redis + Django

---

## 📋 PRE-REQUISITOS

### Servicios Requeridos

```bash
# Verificar que estén corriendo:
docker ps | grep -E "redis|postgres|celery"
```

Debe mostrar:
- ✅ `redis` (puerto 6379)
- ✅ `postgres` (puerto 5432)
- ✅ `celery_worker` (opcional si ya existe)
- ✅ `celery_beat` (opcional si ya existe)

---

## 🔧 PASO 1: CONFIGURACIÓN DE VARIABLES DE ENTORNO

Agregar al archivo `.env` o `docker-compose.yml`:

```bash
# Redis (Broker y Result Backend)
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Celery Workers
CELERY_WORKER_CONCURRENCY=4  # Ajustar según CPU
CELERY_WORKER_MAX_TASKS_PER_CHILD=1000

# Timezone
CELERY_TIMEZONE=America/Santiago
CELERY_ENABLE_UTC=True

# Logging
CELERY_LOG_LEVEL=INFO
```

---

## 🐳 PASO 2: DOCKER COMPOSE - Agregar Servicios Celery

### Opción A: Agregar a `docker-compose.production.yml`

```yaml
services:
  # ... servicios existentes (django, postgres, redis) ...

  # ========================================================================
  # CELERY WORKER - Procesa tasks de telemetría
  # ========================================================================
  celery_worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: celery_worker_telemetry
    command: celery -A api.celery_app worker --loglevel=info --concurrency=4 -Q telemetry,dga,alerts,reports
    volumes:
      - ./api:/app/api
      - /opt/smarthydro/celery_logs:/app/logs
    environment:
      - DJANGO_SETTINGS_MODULE=api.settings
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
    depends_on:
      - redis
      - postgres
    restart: unless-stopped
    networks:
      - smarthydro_network

  # ========================================================================
  # CELERY BEAT - Scheduler (reemplaza django-crontab)
  # ========================================================================
  celery_beat:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: celery_beat_scheduler
    command: celery -A api.celery_app beat --loglevel=info
    volumes:
      - ./api:/app/api
      - /opt/smarthydro/celery_logs:/app/logs
    environment:
      - DJANGO_SETTINGS_MODULE=api.settings
      - CELERY_BROKER_URL=redis://redis:6379/1
    depends_on:
      - redis
      - celery_worker
    restart: unless-stopped
    networks:
      - smarthydro_network

  # ========================================================================
  # CELERY FLOWER - Monitoring Dashboard (OPCIONAL)
  # ========================================================================
  celery_flower:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: celery_flower_monitor
    command: celery -A api.celery_app flower --port=5555
    ports:
      - "5555:5555"
    environment:
      - DJANGO_SETTINGS_MODULE=api.settings
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
    depends_on:
      - celery_worker
    restart: unless-stopped
    networks:
      - smarthydro_network
```

---

## 📂 PASO 3: CREAR DIRECTORIOS DE LOGS

```bash
sudo mkdir -p /opt/smarthydro/celery_logs
sudo chown -R 1000:1000 /opt/smarthydro/celery_logs
```

---

## 🏗️ PASO 4: BUILD Y DEPLOY

### Deploy Completo (Primera vez)

```bash
# 1. Stop servicios legacy de cron si existen
docker-compose -f docker-compose.production.yml stop cron

# 2. Build nuevos servicios
docker-compose -f docker-compose.production.yml build celery_worker celery_beat celery_flower

# 3. Start servicios Celery
docker-compose -f docker-compose.production.yml up -d celery_worker celery_beat celery_flower

# 4. Verificar que estén corriendo
docker-compose -f docker-compose.production.yml ps
```

### Deploy Incremental (Solo actualizar código)

```bash
# Si solo cambiaste código Python:
docker-compose -f docker-compose.production.yml restart celery_worker celery_beat

# Si cambiaste configuración de Celery (celery_app.py):
docker-compose -f docker-compose.production.yml stop celery_worker celery_beat
docker-compose -f docker-compose.production.yml up -d celery_worker celery_beat
```

---

## ✅ PASO 5: VERIFICACIÓN

### 1. Verificar que los servicios estén UP

```bash
docker-compose -f docker-compose.production.yml ps

# Debe mostrar:
# celery_worker_telemetry    Up
# celery_beat_scheduler      Up
# celery_flower_monitor      Up (opcional)
```

### 2. Verificar logs de Celery Worker

```bash
docker logs celery_worker_telemetry --tail=50

# Debe mostrar:
# [2026-01-17 16:00:00] celery.worker: Ready to accept tasks
# [2026-01-17 16:00:00] celery.app.trace: Task api.core.tasks.telemetry.collect_telemetry...
```

### 3. Verificar logs de Celery Beat

```bash
docker logs celery_beat_scheduler --tail=30

# Debe mostrar los schedules configurados:
# collect-telemetry-1min: Every 60 seconds
# collect-telemetry-5min: Every 5 minutes
# collect-telemetry-60min: Every hour
```

### 4. Verificar que Redis esté funcionando

```bash
docker exec -it redis redis-cli ping
# Debe retornar: PONG

# Ver keys de Celery
docker exec -it redis redis-cli KEYS 'celery*'
```

### 5. Acceder a Flower Dashboard (opcional)

```
http://localhost:5555
```

Deberías ver:
- ✅ Workers activos
- ✅ Tasks en ejecución
- ✅ Estadísticas en tiempo real

---

## 🧪 PASO 6: TESTING

### Test Manual de Telemetría

```bash
# Entrar al contenedor Django
docker exec -it django_api_secure python manage.py shell

# Ejecutar task manualmente
>>> from api.core.tasks.telemetry import collect_telemetry
>>> result = collect_telemetry("5")
>>> print(result)
# {'status': 'dispatched', 'points_count': 10, 'frequency': '5', ...}
```

### Test con pytest

```bash
docker exec -it django_api_secure pytest tests/telemetry/test_unified_telemetry.py -v
```

### Verificar procesamiento en tiempo real

```bash
# Terminal 1: Ver logs worker
docker logs -f celery_worker_telemetry

# Terminal 2: Trigger manual
docker exec -it django_api_secure python -c "
from api.core.tasks.telemetry import collect_telemetry
collect_telemetry.delay('1')
"

# En Terminal 1 deberías ver:
# [2026-01-17 16:05:00] Task collect_telemetry[...] received
# [2026-01-17 16:05:01] 🚀 [TELEMETRY] Starting collection for 1min frequency
# [2026-01-17 16:05:02] ✅ [TELEMETRY] Dispatched 15 points in 1 batches
```

---

## 🔄 PASO 7: MIGRACIÓN DESDE DJANGO-CRONTAB (LEGACY)

### Desactivar cronjobs legacy

```bash
# Dentro del contenedor de cron (si existe)
docker exec -it cron_jobs_secure python manage.py crontab remove

# Verificar que estén eliminados
docker exec -it cron_jobs_secure crontab -l
# Debe mostrar: no crontab for root
```

### Remover servicio de cron del docker-compose (opcional)

Comentar o eliminar el servicio `cron` de `docker-compose.production.yml`:

```yaml
# services:
#   cron:  # ← COMENTAR O ELIMINAR
#     ...
```

---

## 📊 PASO 8: MONITORING Y ALERTAS

### Prometheus + Grafana (Opcional)

```yaml
# Agregar a docker-compose.production.yml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=admin
```

**Configuración Prometheus** (`monitoring/prometheus.yml`):

```yaml
scrape_configs:
  - job_name: 'celery'
    static_configs:
      - targets: ['celery_flower:5555']
```

---

## 🚨 TROUBLESHOOTING

### Problema: Worker no procesa tasks

```bash
# 1. Verificar que Redis esté corriendo
docker exec -it redis redis-cli ping

# 2. Verificar que worker esté escuchando la queue correcta
docker logs celery_worker_telemetry | grep "telemetry"

# 3. Purgar queue si está bloqueada
docker exec -it django_api_secure python -c "
from api.celery_app import app
app.control.purge()
"
```

### Problema: Beat no dispara tasks

```bash
# Verificar schedule en Beat
docker logs celery_beat_scheduler | grep "collect-telemetry"

# Reiniciar Beat
docker-compose -f docker-compose.production.yml restart celery_beat
```

### Problema: Tasks fallan silenciosamente

```bash
# Ver errores en logs de worker
docker logs celery_worker_telemetry 2>&1 | grep ERROR

# Ejecutar task en modo sync para ver traceback
docker exec -it django_api_secure python -c "
from api.core.tasks.telemetry import collect_telemetry
collect_telemetry('1')  # Sin .delay() para ver errores
"
```

### Problema: Alto uso de memoria

```bash
# Reducir concurrency
docker-compose -f docker-compose.production.yml stop celery_worker

# Editar docker-compose.yml:
# command: celery -A api.celery_app worker --concurrency=2  # ← Reducir

docker-compose -f docker-compose.production.yml up -d celery_worker
```

---

## 🎯 COMANDOS ÚTILES

```bash
# Ver tasks activas
docker exec celery_worker_telemetry celery -A api.celery_app inspect active

# Ver tasks programadas
docker exec celery_beat_scheduler celery -A api.celery_app inspect scheduled

# Ver workers registrados
docker exec celery_worker_telemetry celery -A api.celery_app inspect registered

# Estadísticas de workers
docker exec celery_worker_telemetry celery -A api.celery_app inspect stats

# Purgar todas las tasks pendientes
docker exec django_api_secure python -c "from api.celery_app import app; app.control.purge()"

# Ver queue telemetry
docker exec -it redis redis-cli LLEN celery
```

---

## 📈 MÉTRICAS DE ÉXITO

Después del deployment, verificar:

- ✅ Worker procesa tasks sin errores
- ✅ Beat dispara tasks según schedule
- ✅ Datos de telemetría se guardan en DB
- ✅ Logs muestran procesamiento exitoso
- ✅ Flower dashboard muestra actividad
- ✅ No hay memory leaks (monitorear por 24h)

---

## 🔗 RECURSOS

- [Documentación Celery](https://docs.celeryproject.org/)
- [Arquitectura Unificada](./ARQUITECTURA_UNIFICADA_ANALISIS.md)
- [Tests](./tests/telemetry/test_unified_telemetry.py)
- [Código Task Unificado](./api/core/tasks/telemetry.py)

---

## ✅ CHECKLIST DE DEPLOYMENT

- [ ] Redis corriendo y accesible
- [ ] Variables de entorno configuradas
- [ ] Servicios Celery agregados a docker-compose
- [ ] Directorios de logs creados
- [ ] Build y start de servicios
- [ ] Verificación de logs (sin errores)
- [ ] Test manual exitoso
- [ ] Tests automatizados pasando
- [ ] Cronjobs legacy desactivados
- [ ] Monitoring configurado (Flower/Prometheus)
- [ ] Documentación actualizada en CLAUDE.md

---

**¡DEPLOYMENT COMPLETADO!** 🎉

El sistema de telemetría unificado está ahora en producción con procesamiento paralelo, retry automático y monitoring en tiempo real.
