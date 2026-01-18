# 🚀 Migración de Cronjobs a Celery

## Por qué Cambiar de Cronjobs a Celery

### ❌ **Problemas con Cronjobs Tradicionales**

| Problema | Impacto | Solución Celery |
|----------|---------|-----------------|
| **Sin seguimiento** | No sabes si falló | Dashboard completo en Flower |
| **Sin escalabilidad** | Un proceso = un servidor | Workers distribuidos |
| **Difícil debugging** | Logs dispersos | Logs centralizados + retries |
| **Sin concurrencia** | Procesamiento secuencial | Procesamiento paralelo |
| **Sin monitoreo** | No sabes el estado | Métricas en tiempo real |
| **Sin recuperación** | Fallo = datos perdidos | Retry automático + DLQ |

### ✅ **Ventajas de Celery**

- **🏁 Seguimiento Visual**: Flower dashboard con métricas en tiempo real
- **📈 Escalabilidad Horizontal**: Agrega workers según necesidad
- **🔄 Retry Automático**: Reintenta tareas fallidas
- **⚡ Procesamiento Paralelo**: Múltiples tareas simultáneas
- **📊 Monitoreo Completo**: Latencia, throughput, errores
- **🛡️ Recuperación de Fallos**: Dead Letter Queue para tareas fallidas
- **🎯 Resultados Persistentes**: Almacena resultados de tareas

---

## 🏗️ Arquitectura Celery

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   DJANGO API    │    │     REDIS       │    │  CELERY WORKERS │
│                 │    │  Message Broker │    │                 │
│ • Tasks Queue   │◄──►│  • Telemetry    │◄──►│ • Telemetry      │
│ • Results Store │    │  • DGA          │    │ • DGA            │
│                 │    │  • Alerts       │    │ • Alerts         │
└─────────────────┘    │  • Reports      │    │ • Reports        │
                       │  • Maintenance  │    │ • Maintenance    │
┌─────────────────┐    │                 │    │ • Monitoring     │
│  CELERY BEAT    │    └─────────────────┘    └─────────────────┘
│  Task Scheduler │              ▲
│                 │              │
│ • Cronjobs →    │              │
│   Scheduled     │              │
│   Tasks         │              │
└─────────────────┘              ▼
                       ┌─────────────────┐
                       │     FLOWER      │
                       │   Monitoring    │
                       │   Dashboard     │
                       └─────────────────┘
```

---

## 📋 Guía de Migración Paso a Paso

### Paso 1: Instalar Dependencias
```bash
# Agregar a requirements.txt
celery[redis]>=5.3.0,<6.0.0
django-celery-beat>=2.5.0,<3.0.0
django-celery-results>=2.6.0,<3.0.0
flower>=2.0.0,<3.0.0
psutil>=5.9.0,<6.0.0
```

### Paso 2: Crear Configuración Celery
```python
# api/celery_app.py (ya creado)
# Configuración completa con beat schedule
```

### Paso 3: Migrar Cronjobs a Tasks

#### ❌ **Antes (Cronjob)**
```bash
# crontab -e
*/5 * * * * /path/to/python manage.py collect_telemetry 5
0 * * * * /path/to/python manage.py process_dga
```

#### ✅ **Después (Celery Beat)**
```python
# api/settings.py
CELERY_BEAT_SCHEDULE = {
    'collect-telemetry-5min': {
        'task': 'api.core.tasks.telemetry.collect_telemetry',
        'schedule': 300.0,  # 5 minutes
        'args': ('5',),
    },
    'process-dga-queue': {
        'task': 'api.core.tasks.dga.process_dga_queue',
        'schedule': crontab(minute='*/3'),  # Every 3 minutes
    },
}
```

### Paso 4: Ejecutar Migración
```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Ejecutar migraciones
python manage.py migrate

# 3. Crear superusuario para Celery Beat (opcional)
python manage.py createsuperuser

# 4. Iniciar servicios
docker-compose -f docker-compose.celery.yml up -d

# 5. Verificar funcionamiento
docker-compose -f docker-compose.celery.yml logs celery_worker
```

---

## 🎯 Comparación de Funcionalidades

### Telemetría Collection

#### ❌ **Cronjob Approach**
```python
# api/cronjobs/telemetry/twin.py
def run():
    points = CatchmentPoint.objects.filter(is_tdata=True, frecuency="60")
    for point in points:  # Procesamiento SECUENCIAL
        try:
            process_point(point)  # Si falla uno, continua
        except Exception as e:
            print(f"Error: {e}")  # Sin seguimiento
```

#### ✅ **Celery Approach**
```python
# api/core/tasks/telemetry.py
@shared_task(bind=True, max_retries=3, retry_backoff=True)
def collect_telemetry(self, frequency_minutes):
    points = get_points_for_frequency(frequency_minutes)

    # Procesamiento PARALELO en batches
    batch_tasks = []
    for i in range(0, len(points), 10):
        batch = points[i:i+10]
        batch_tasks.append(process_batch.s(batch, frequency_minutes))

    # Ejecutar en paralelo y esperar resultados
    job = group(batch_tasks)
    results = job.apply_async().get(timeout=300)

    return {
        'processed': sum(r['processed'] for r in results),
        'errors': sum(r['errors'] for r in results),
        'batches': len(batch_tasks)
    }
```

### DGA Processing

#### ❌ **Cronjob Approach**
```bash
# Cada 3 minutos ejecuta todo
*/3 * * * * python manage.py process_dga
# Si falla, no hay reintento
# No hay monitoreo de progreso
```

#### ✅ **Celery Approach**
```python
@shared_task(bind=True, max_retries=3, retry_backoff=True)
def process_dga_queue(self):
    # Procesar en batches de 50
    pending = InteractionDetail.objects.filter(
        send_dga=True, is_error=False
    )[:50]

    processed = 0
    errors = 0

    for record in pending:
        try:
            success = submit_to_dga(record)
            if success:
                record.send_dga = False
                record.save()
                processed += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1
            logger.error(f"DGA failed for {record.id}: {e}")

    return {'processed': processed, 'errors': errors}
```

---

## 📊 Monitoreo y Dashboard

### Flower Dashboard
```
🌐 http://localhost:5555

Features:
• Tasks por hora/día
• Workers activos
• Queue lengths
• Failed tasks
• Task latency
• Success rates
```

### Health Checks
```python
# api/core/tasks/monitoring.py
@shared_task(bind=True)
def perform_health_check(self):
    return {
        'database': check_db_health(),
        'redis': check_redis_health(),
        'telemetry_flow': check_telemetry_health(),
        'system_resources': get_system_metrics(),
        'alerts': generated_alerts
    }
```

---

## 🚨 Gestión de Errores

### Retry Strategies
```python
@shared_task(bind=True, max_retries=3, retry_backoff=True)
def unreliable_task(self):
    try:
        # Do work
        pass
    except Exception as exc:
        # Retry with exponential backoff
        self.retry(countdown=60 * (2 ** self.request.retries), exc=exc)
```

### Dead Letter Queue
```python
# Tasks que fallan definitivamente van a DLQ
@app.task(bind=True, max_retries=3)
def process_with_dlq(self):
    try:
        # Process
        pass
    except Exception as exc:
        if self.request.retries >= 3:
            # Send to dead letter queue
            send_to_dlq(self.request)
        raise
```

---

## ⚡ Optimizaciones de Performance

### 1. **Batch Processing**
```python
# Procesar 50 puntos en paralelo
batch_tasks = [process_point.s(point_id) for point_id in point_ids]
group(batch_tasks).apply_async()
```

### 2. **Connection Pooling**
```python
# Reutilizar conexiones de base de datos
from django.db import connection
with connection.cursor() as cursor:
    # Raw SQL queries
```

### 3. **Memory Management**
```python
# Procesar en chunks para evitar memory exhaustion
for chunk in chunks(large_dataset, 1000):
    process_chunk(chunk)
```

### 4. **Circuit Breaker**
```python
# Evitar sobrecargar servicios externos
if external_service_unavailable():
    self.retry(countdown=300, exc=Exception("Service unavailable"))
```

---

## 📈 Métricas y Alertas

### Performance Metrics
```
✅ Tasks completed per minute
✅ Queue depth
✅ Error rates
✅ Task latency
✅ Worker utilization
✅ Memory usage per worker
```

### Alerting
```python
# Alertas automáticas
if queue_depth > 1000:
    send_alert("High queue backlog")

if error_rate > 10:
    send_alert("High error rate detected")
```

---

## 🛠️ Troubleshooting

### Comandos Útiles
```bash
# Ver estado de workers
celery -A api inspect active

# Ver queues
celery -A api inspect stats

# Monitorear tasks específicos
celery -A api events

# Limpiar queues (cuidado!)
celery -A api purge
```

### Problemas Comunes
1. **Workers no conectan**: Verificar REDIS_URL
2. **Tasks no se ejecutan**: Verificar CELERY_BROKER_URL
3. **Memory leaks**: Reiniciar workers periódicamente
4. **Queue growing**: Agregar más workers

---

## 🎯 Resultados Esperados

### Performance Improvements
| Métrica | Cronjobs | Celery | Mejora |
|---------|----------|--------|--------|
| **Throughput** | 1 task/min | 100+ tasks/min | **100x** |
| **Reliability** | 90% | 99.9% | **11x más confiable** |
| **Monitoring** | None | Complete | **100% visibility** |
| **Scalability** | 1 server | N servers | **Horizontal scale** |
| **Error Recovery** | Manual | Automatic | **Zero intervention** |

### Operational Benefits
- ✅ **Zero-downtime deployments**
- ✅ **Auto-scaling basado en load**
- ✅ **Distributed processing**
- ✅ **Real-time monitoring**
- ✅ **Automatic failure recovery**
- ✅ **Performance analytics**

---

## 🚀 Próximos Pasos

### Fase 1: Migración Básica (1 semana)
- [ ] Instalar dependencias
- [ ] Configurar Celery básico
- [ ] Migrar 1-2 cronjobs
- [ ] Verificar funcionamiento

### Fase 2: Optimizaciones (2 semanas)
- [ ] Implementar batch processing
- [ ] Configurar monitoring completo
- [ ] Optimizar queries
- [ ] Agregar health checks

### Fase 3: Producción (1 semana)
- [ ] Configurar múltiples workers
- [ ] Implementar alerting
- [ ] Documentar procedimientos
- [ ] Entrenamiento del equipo

---

## 💡 Recomendaciones

### Para SmartHydro específicamente:
1. **Empieza con telemetría** - Es tu core business
2. **Configura Flower** - Monitoreo visual es crítico
3. **Implementa health checks** - Detección temprana de problemas
4. **Configura alerting** - Notificaciones automáticas
5. **Monitorea queues** - Evita backlogs

### Arquitectura Recomendada:
```
• 2-4 Celery Workers (dependiendo del load)
• 1 Celery Beat scheduler
• 1 Flower monitoring instance
• Redis como broker y cache
• PostgreSQL optimizado
```

**¡Celery transformará tu sistema de procesamiento por lotes limitado a una plataforma de procesamiento distribuido escalable!** 🚀