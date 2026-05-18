# Plan Técnico de Mejoras — SmartHydro

> **Auditoría base:** 2026-05-14  
> **Prioridad:** Alta | **Riesgo:** Medio-Alto | **Requiere:** Validación en staging

---

## 1. Seguridad (Prioridad CRÍTICA)

### 1.1 Credenciales en código
**Problema:** `getters/tdata.py:12-13` tiene usuario/password TDATA hardcodeados.
**Solución:**
1. Crear variables de entorno: `TDATA_USERNAME`, `TDATA_PASSWORD`
2. Modificar `getters/tdata.py` para leer de `os.environ.get(...)`
3. Rotar las credenciales actuales (ya están expuestas en git)
4. Agregar a `.env` y `docker-compose.production.secure.yml`

### 1.2 Redis sin autenticación
**Problema:** `redis_secure` no tiene `requirepass`.
**Solución:**
1. Generar password fuerte
2. Agregar `command: redis-server --requirepass ${REDIS_PASSWORD}` en docker-compose
3. Configurar `CACHES` en `settings.py` con `PASSWORD`

### 1.3 Bind mount en producción
**Problema:** `./:/app` expone `.git/`, `.env`, y permite modificar código en caliente.
**Solución:**
1. Copiar código en build time (`COPY . /app/`) en vez de bind mount
2. Si se necesita hot-reload para emergencias, usar volumen restringido a solo `api/`

### 1.4 Imágenes con `latest`
**Problema:** `jwilder/nginx-proxy:latest`, `jrcs/letsencrypt-nginx-proxy-companion:latest`
**Solución:** Pin a versiones específicas (ej. `nginx-proxy:1.6`, `letsencrypt-companion:2.4`)

---

## 2. Base de Datos (Prioridad ALTA)

### 2.1 Índices faltantes
**Impacto:** Queries lentas en tablas grandes (InteractionDetail, CatchmentPoint).
**Tablas/campos a indexar:**

```python
# CatchmentPoint
project = models.ForeignKey(..., db_index=True)
owner_user = models.ForeignKey(..., db_index=True)

# NotificationsCatchment
point_catchment = models.ForeignKey(..., db_index=True)

# ProfileDataConfigCatchment
point_catchment = models.ForeignKey(..., db_index=True)

# DgaDataConfigCatchment
point_catchment = models.ForeignKey(..., db_index=True)

# FileCatchment
point_catchment = models.ForeignKey(..., db_index=True)

# ResponseNotificationsCatchment
notification = models.ForeignKey(..., db_index=True)
user = models.ForeignKey(..., db_index=True)
```

**Migración:** `makemigrations` → probar en staging → aplicar en producción en horario de bajo tráfico.

### 2.2 DecimalField inválido
**Problema:** `flow_granted_dga = models.DecimalField(max_length=1200, ...)`
**Solución:**
```python
flow_granted_dga = models.DecimalField(
    max_digits=15,
    decimal_places=2,
    default=Decimal('0.00'),
)
```
⚠️ Requiere migración y verificación de datos existentes.

### 2.3 IntegerField con default float
**Problema:** `d6 = models.IntegerField(default=0.0, ...)`
**Solución:** `default=0`

---

## 3. Performance API (Prioridad ALTA)

### 3.1 N+1 Query en points_status
**Archivo:** `views/management.py:155-188`

**Actual:**
```python
for point in queryset:
    last = InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition').first()
    has_telemetry = ProfileDataConfigCatchment.objects.filter(point_catchment=point, is_telemetry=True).exists()
```

**Mejorado:**
```python
# Precalcular últimas interacciones
last_interactions = {
    i.catchment_point_id: i
    for i in InteractionDetail.objects.filter(
        catchment_point__in=queryset
    ).order_by('catchment_point', '-date_time_medition').distinct('catchment_point')
}

# Precalcular puntos con telemetría
 telemetry_point_ids = set(
    ProfileDataConfigCatchment.objects.filter(
        point_catchment__in=queryset, is_telemetry=True
    ).values_list('point_catchment_id', flat=True)
)

for point in queryset:
    last = last_interactions.get(point.id)
    has_telemetry = point.id in telemetry_point_ids
```

### 3.2 Paginación faltante
**Problema:** `ClientViewSet`, `ProjectCatchmentsViewSet`, `CatchmentPointViewSet` devuelven `.all()` sin límite.
**Solución:**
```python
class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    pagination_class = StandardResultsSetPagination  # 100 items/página
```

⚠️ **Riesgo:** El frontend Ikolu puede no soportar paginación en estos endpoints. Verificar antes de implementar.

---

## 4. Telemetría (Prioridad ALTA)

### 4.1 Race condition en total.py
**Archivo:** `controllers/total.py:160-162`

**Actual:**
```python
profile.addition = offset + int(amount_to_add)
profile.save()
```

**Mejorado:**
```python
from django.db.models import F

ProfileDataConfigCatchment.objects.filter(id=profile.id).update(
    addition=F('addition') + int(amount_to_add)
)
```

⚠️ **Riesgo:** Cambia el flujo de ejecución. Requiere test exhaustivo en staging.

### 4.2 Pérdida de precisión en addition
**Problema:** `int(amount_to_add)` trunca decimales.
**Opciones:**
- Cambiar `addition` a `FloatField` o `DecimalField`
- O redondear en vez de truncar: `round(amount_to_add)`

⚠️ Requiere análisis de impacto en datos históricos.

---

## 5. Código y Mantenibilidad (Prioridad MEDIA)

### 5.1 Prints de debug en cronjobs
**Problema:** 100+ `print()` en `api/cronjobs/`. Contaminan logs y dificultan debugging.
**Solución:** Reemplazar por `logging.getLogger(__name__)` con niveles apropiados.

### 5.2 Excepciones silenciadas
**Archivos:** `reports.py`, `interaction_detail.py`
**Problema:** `except Exception: pass` oculta errores.
**Solución:** Al menos loggear el error antes de continuar.

### 5.3 Código comentado muerto
**Archivos:** `nettra_f5.py`, `novus.py`, `twin*.py`
**Solución:** Eliminar bloques comentados obsoletos.

---

## 6. Docker y Infraestructura (Prioridad MEDIA)

### 6.1 Dockerfile optimizado
**Problemas actuales:**
- Imagen base `python:3.11` (full, no slim)
- Instala `vim`, `nginx` innecesarios
- Cache de apt no limpiada
- `ADD` en vez de `COPY`

### 6.2 Gunicorn config
**Problemas:**
- `workers = 3` hardcodeado (comentario dice auto-detect)
- `max_requests = 1000` muy agresivo

### 6.3 Health checks
**Falta:** `letsencrypt` no tiene healthcheck.

---

## 📋 Orden de Implementación Recomendado

1. **Fase 0 (inmediato, seguro):**
   - ✅ Settings de seguridad (ya aplicado)
   - ✅ Limpiar prints de tokens (ya aplicado)
   - ✅ Limpiar imports no usados (ya aplicado)

2. **Fase 1 (requiere staging):**
   - Índices en modelos
   - Fix DecimalField / IntegerField
   - N+1 query en points_status

3. **Fase 2 (requiere validación exhaustiva):**
   - Paginación en endpoints
   - Race condition en total.py
   - Precisión de addition

4. **Fase 3 (infraestructura):**
   - Redis auth
   - Bind mount → COPY
   - Pin imágenes Docker
   - Optimizar Dockerfile
