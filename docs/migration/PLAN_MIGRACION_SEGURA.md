# 🔄 PLAN DE MIGRACIÓN SEGURA - Legacy a Celery V3.1

**Estado Actual**: Archivos legacy existen pero **NO se ejecutan** (CRONJOBS eliminados de settings.py)
**Nuevo Sistema**: Celery tasks **listos pero no desplegados** en producción

---

## ⚠️ IMPORTANTE: NO ELIMINAR ARCHIVOS LEGACY TODAVÍA

Los archivos legacy (`twin_f1.py`, `twin_f5.py`, etc.) deben mantenerse como **backup** hasta:

1. ✅ El nuevo sistema Celery esté desplegado en producción
2. ✅ Se verifique que funciona correctamente por **7 días**
3. ✅ Se confirme que NO hay errores críticos
4. ✅ Se valide que la performance es mejor

**Solo después** de esas validaciones, eliminar.

---

## 📋 ESTADO ACTUAL DEL CÓDIGO

### ✅ Archivos Legacy (AÚN EXISTEN, NO SE USAN)

Ubicación: `api/telemetry/ingestion/`

```bash
ls -lh api/telemetry/ingestion/twin*.py api/telemetry/ingestion/nettra*.py api/telemetry/ingestion/novus.py
```

| Archivo | Estado | Usado en CRONJOBS? | Usado en Celery? |
|---------|--------|-------------------|------------------|
| `twin.py` | ✅ Existe | ❌ NO | ❌ NO |
| `twin_f1.py` | ✅ Existe | ❌ NO | ❌ NO |
| `twin_f5.py` | ✅ Existe | ❌ NO | ❌ NO |
| `twin_f10.py` | ✅ Existe | ❌ NO | ❌ NO |
| `nettra.py` | ✅ Existe | ❌ NO | ❌ NO |
| `nettra_f5.py` | ✅ Existe | ❌ NO | ❌ NO |
| `novus.py` | ✅ Existe | ❌ NO | ❌ NO |

### ✅ Nuevo Sistema Celery (LISTO, NO DESPLEGADO)

| Archivo | Estado | En Producción? |
|---------|--------|----------------|
| `api/core/tasks/telemetry.py` | ✅ Creado | ❌ NO (pendiente deployment) |
| `api/celery_app.py` | ✅ Actualizado | ❌ NO (pendiente deployment) |

---

## 🚀 PLAN DE MIGRACIÓN (5 FASES)

### FASE 1: TESTING LOCAL (AHORA) ⚠️ **PENDIENTE**

**Objetivo**: Verificar que el nuevo sistema funciona en desarrollo

```bash
# 1. Verificar que Celery está instalado
pip list | grep celery

# 2. Iniciar Redis (si no está corriendo)
docker-compose up -d redis

# 3. Iniciar Celery Worker en desarrollo
celery -A api.celery_app worker --loglevel=info -Q telemetry

# 4. En otra terminal, iniciar Celery Beat
celery -A api.celery_app beat --loglevel=info

# 5. Verificar logs
# Deberías ver tasks disparándose cada minuto/5min/60min
```

**Validaciones**:
- [ ] Worker arranca sin errores
- [ ] Beat dispara tasks según schedule
- [ ] Tasks procesan puntos correctamente
- [ ] Datos se guardan en `TelemetryRecord`
- [ ] NO hay errores en logs

**Si hay errores**: NO avanzar a Fase 2, arreglar primero.

---

### FASE 2: DEPLOYMENT EN STAGING/DEV (1-2 días)

**Objetivo**: Probar en un entorno similar a producción

```bash
# 1. Agregar servicios Celery a docker-compose.dev.yml
# (Seguir DEPLOYMENT_UNIFIED_TELEMETRY.md)

# 2. Build y start
docker-compose -f docker-compose.dev.yml build celery_worker celery_beat
docker-compose -f docker-compose.dev.yml up -d celery_worker celery_beat

# 3. Monitorear por 24 horas
docker logs -f celery_worker_telemetry
```

**Validaciones**:
- [ ] Tasks se ejecutan cada 1/5/10/60 minutos
- [ ] Datos en DB coinciden con lo esperado
- [ ] Performance es igual o mejor que legacy
- [ ] NO hay memory leaks (monitorear RAM por 24h)
- [ ] Error rate < 5%

---

### FASE 3: DEPLOYMENT EN PRODUCCIÓN (1 semana de prueba)

**Objetivo**: Correr en producción con monitoreo intensivo

```bash
# 1. Backup de DB antes de deployment
pg_dump smarthydro > backup_pre_celery_$(date +%Y%m%d).sql

# 2. Deploy servicios Celery
docker-compose -f docker-compose.production.yml build celery_worker celery_beat
docker-compose -f docker-compose.production.yml up -d celery_worker celery_beat

# 3. Verificar que arrancaron
docker-compose -f docker-compose.production.yml ps

# 4. Monitorear logs en tiempo real (primeras 2 horas)
docker logs -f celery_worker_telemetry
```

**Validaciones durante 7 días**:
- [ ] Día 1: Verificar cada hora que tasks se ejecutan
- [ ] Día 2: Comparar datos con día anterior (consistencia)
- [ ] Día 3-7: Monitorear error rate, performance, RAM usage
- [ ] Día 7: Revisar métricas en Flower/Prometheus

**KPIs de Éxito**:
- ✅ Error rate < 2%
- ✅ Datos 100% consistentes con legacy
- ✅ Performance igual o mejor
- ✅ NO memory leaks
- ✅ NO downtime

---

### FASE 4: ELIMINAR ARCHIVOS LEGACY (Después de 7 días exitosos)

**Objetivo**: Limpiar código legacy confirmando que ya no se necesita

```bash
# Solo si FASE 3 fue 100% exitosa por 7 días

# 1. Mover archivos legacy a carpeta de backup
mkdir -p api/telemetry/ingestion/LEGACY_BACKUP_2026_01_24
mv api/telemetry/ingestion/twin*.py api/telemetry/ingestion/LEGACY_BACKUP_2026_01_24/
mv api/telemetry/ingestion/nettra*.py api/telemetry/ingestion/LEGACY_BACKUP_2026_01_24/
mv api/telemetry/ingestion/novus.py api/telemetry/ingestion/LEGACY_BACKUP_2026_01_24/

# 2. Commit con mensaje claro
git add .
git commit -m "chore: Archive legacy telemetry files after successful Celery migration

- Moved twin*.py, nettra*.py, novus.py to LEGACY_BACKUP_2026_01_24/
- New Celery system running successfully for 7 days
- Zero critical errors, performance improved by ~4x
- Kept as backup for 30 days before final deletion"

# 3. NO push todavía, esperar 30 días más
```

**IMPORTANTE**: Los archivos quedan en `LEGACY_BACKUP_2026_01_24/` por **30 días más** antes de eliminación definitiva.

---

### FASE 5: ELIMINACIÓN DEFINITIVA (Después de 30 días de backup)

**Objetivo**: Eliminar archivos legacy definitivamente

```bash
# Solo después de 30 días sin incidentes

# 1. Eliminar carpeta de backup
rm -rf api/telemetry/ingestion/LEGACY_BACKUP_2026_01_24/

# 2. Commit final
git add .
git commit -m "chore: Remove legacy telemetry files (backup expired)

- Legacy files successfully replaced by Celery V3.1 unified system
- 37 days of successful operation (7 days prod + 30 days backup)
- Zero rollback incidents"

git push origin main
```

---

## 📊 CHECKLIST DE VALIDACIÓN

### Antes de eliminar legacy (CRÍTICO):

- [ ] **7 días** de operación exitosa en producción
- [ ] **Error rate < 2%** confirmado
- [ ] **Performance >= legacy** confirmado
- [ ] **NO memory leaks** confirmado
- [ ] **Datos 100% consistentes** confirmado
- [ ] **Backup de DB** realizado
- [ ] **Archivos legacy movidos a BACKUP** (no eliminados)
- [ ] **Equipo avisado** del cambio

### Antes de eliminación definitiva (30 días después):

- [ ] **30 días** sin incidentes relacionados
- [ ] **NO rollback** necesario
- [ ] **Métricas de Flower** muestran estabilidad
- [ ] **Feedback del equipo** positivo

---

## 🚨 PLAN DE ROLLBACK

Si algo falla en FASE 3 (producción):

```bash
# 1. PARAR Celery inmediatamente
docker-compose -f docker-compose.production.yml stop celery_worker celery_beat

# 2. RESTAURAR CRONJOBS legacy en settings.py
# (Descomentar sección CRONJOBS)

# 3. RESTART cron container
docker-compose -f docker-compose.production.yml restart cron

# 4. VERIFICAR que legacy funciona
docker exec cron_jobs_secure crontab -l

# 5. INVESTIGAR qué falló en Celery
docker logs celery_worker_telemetry > celery_error_$(date +%Y%m%d_%H%M%S).log
```

**Tiempo de rollback**: < 5 minutos

---

## 📝 CRONOGRAMA ESTIMADO

| Fase | Duración | Inicio | Fin Estimado |
|------|----------|--------|--------------|
| **FASE 1: Testing Local** | 1-2 días | HOY | 2026-01-19 |
| **FASE 2: Staging** | 1-2 días | 2026-01-19 | 2026-01-21 |
| **FASE 3: Producción** | 7 días | 2026-01-21 | 2026-01-28 |
| **FASE 4: Backup Legacy** | 1 día | 2026-01-28 | 2026-01-29 |
| **FASE 5: Eliminación** | - | 2026-02-28 | 2026-02-28 |

**Total**: ~40 días desde hoy hasta eliminación definitiva

---

## ✅ RESUMEN

**ESTADO ACTUAL**:
- ✅ Código nuevo listo
- ✅ Tests escritos (25+)
- ✅ Documentación completa
- ⚠️ **NO desplegado en producción**
- ⚠️ **Legacy files AÚN EXISTEN (como backup)**

**PRÓXIMO PASO INMEDIATO**:
👉 **FASE 1: Testing Local** - Probar que Celery funciona en tu máquina

**NO ELIMINAR LEGACY HASTA**:
- ✅ 7 días exitosos en producción
- ✅ + 30 días de backup sin incidentes

---

**La migración es SEGURA, pero GRADUAL. No hay prisa en eliminar legacy.**
