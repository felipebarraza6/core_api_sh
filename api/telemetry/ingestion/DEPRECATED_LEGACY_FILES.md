# ⚠️ ARCHIVOS LEGACY DEPRECADOS

**Fecha de deprecación**: 2026-01-17
**Versión**: V3.1 Unificada
**Reemplazados por**: `api/core/tasks/telemetry.py`

---

## 🔴 ARCHIVOS MARCADOS COMO OBSOLETOS

Los siguientes archivos han sido **REEMPLAZADOS** por el sistema unificado de Celery tasks y **NO deben ser usados** en nuevos desarrollos:

### Ingesta por Frecuencia (Duplicados)

| Archivo | Líneas | Reemplazado por |
|---------|--------|----------------|
| `twin.py` | 109 | `collect_telemetry("60")` |
| `twin_f1.py` | 110 | `collect_telemetry("1")` |
| `twin_f5.py` | 100 | `collect_telemetry("5")` |
| `twin_f10.py` | 100 | `collect_telemetry("10")` |
| `nettra.py` | ~100 | `collect_telemetry(freq)` |
| `nettra_f5.py` | ~100 | `collect_telemetry("5")` |
| `novus.py` | ~100 | `collect_telemetry(freq)` |

**Razón**: Código 92% duplicado, solo difieren en el filtro `frecuency="X"`.

---

## ✅ NUEVO SISTEMA UNIFICADO

### Ubicación
```
api/core/tasks/telemetry.py
```

### Uso

**Celery Beat (Automático):**
```python
# Configurado en api/celery_app.py
# Se ejecuta automáticamente cada N minutos
```

**Manual (Testing/Debug):**
```python
from api.core.tasks.telemetry import collect_telemetry

# Procesar puntos de frecuencia 1 minuto
collect_telemetry.delay("1")  # Async

# Procesar puntos de frecuencia 5 minutos
collect_telemetry("5")  # Sync
```

---

## 🔄 MIGRACIÓN

### Si estabas usando:

```python
# ❌ ANTIGUO (NO USAR)
from api.telemetry.ingestion.twin_f1 import run as twin_f1_run
twin_f1_run()
```

### Ahora usa:

```python
# ✅ NUEVO (USAR)
from api.core.tasks.telemetry import collect_telemetry
collect_telemetry.delay("1")
```

---

## 📅 CRONOGRAMA DE ELIMINACIÓN

- **2026-01-17**: Marcados como deprecados (HOY)
- **2026-02-17**: Advertencias en logs si se usan
- **2026-03-17**: Eliminación física de archivos

---

## 🆘 SOPORTE

Si encuentras problemas con el nuevo sistema:

1. **Logs**: `docker logs celery_worker --tail=100`
2. **Monitoring**: Celery Flower en `http://localhost:5555`
3. **Testing**: `pytest tests/telemetry/test_unified_telemetry.py -v`

---

## 📊 VENTAJAS DEL NUEVO SISTEMA

| Característica | Legacy | Nuevo |
|----------------|--------|-------|
| Código duplicado | Sí (92%) | No |
| Procesamiento | Secuencial | Paralelo (batches) |
| Retry automático | No | Sí (3 intentos) |
| Monitoring | Logs dispersos | Celery Flower + Prometheus |
| Escalabilidad | Limitada | Alta (workers independientes) |
| Trazabilidad | Sin device_id | Con device_id en metadata |

---

## 🔗 REFERENCIAS

- [Documentación completa](../../../ARQUITECTURA_UNIFICADA_ANALISIS.md)
- [Task unificado](../../core/tasks/telemetry.py)
- [Tests](../../../tests/telemetry/test_unified_telemetry.py)
- [Celery config](../../celery_app.py)
