# Milestone 8 — Shadow mode para totales

> Estado: **cerrado** — shadow mode descubre la variable void por su campo de salida y compara totales con legacy.  
> Fecha cierre: 2026-07-06  
> Objetivo: tener confianza para migrar dispositivos reales de legacy a void validando paridad de totales.

---

## 1. Contexto

El **Milestone 7** cerró con el totalizador robusto.  
El **Milestone 8** permite validar que los totales de void coinciden con los de legacy antes de reemplazar el procesamiento en producción.

El shadow mode existente comparaba por variable interna. Eso forzaba a que la variable void se llamara igual que el campo legacy. Ahora el shadow descubre la variable void a partir del `output_field` configurado, manteniendo la coherencia del diseño flexible de void.

---

## 2. Entregables

| Entregable | Estado |
|---|---|
| `ShadowService.run_for_output_field()` | ✅ |
| Descubrimiento de variable por `output_field`/`internal_variable` | ✅ |
| Tolerancias por campo (total, flow, nivel, water_table) | ✅ |
| Endpoint `POST /void/points/<id>/shadow/` | ✅ |
| Tarea Celery `void_shadow_totals` | ✅ |
| `totalizer` agregado a choices de `DeviceVariableConfig` | ✅ |
| Tests de shadow para totales | ✅ 4 tests |
| Tests de void completos | ✅ 149/149 OK |
| Documentación actualizada | ✅ |

---

## 3. Cómo funciona

### Descubrimiento de variable

```python
# Busca la DeviceVariableConfig activa cuyo output_field (o internal_variable) sea 'total'
config = service._find_config_for_output(device, "total")
# Usa config.internal_variable para leer ProcessedReading
```

Esto permite que un device tenga:

```
source_variable="pulses"
internal_variable="totalizado"
output_field="total"
```

Y el shadow compara `ProcessedReading.total` contra `InteractionDetail.total`.

### Tolerancias

| Campo | Tolerancia |
|---|---|
| `total` | 1.0 m³ (legacy redondea a int) |
| `flow` | 0.01 |
| `nivel` | 0.01 |
| `water_table` | 0.01 |

---

## 4. API

### Ejecutar shadow para un punto

```bash
POST /void/points/<id>/shadow/
{
  "output_field": "total",
  "window_minutes": 70,
  "ingest": true,
  "process": true
}
```

Respuesta:

```json
{
  "run_id": 42,
  "status": "completed",
  "variable": "totalizado",
  "output_field": "total",
  "legacy_count": 12,
  "void_count": 12,
  "matched_count": 11,
  "mismatched_count": 1,
  "legacy_only_count": 0,
  "void_only_count": 0,
  "error_message": ""
}
```

### Tarea Celery

```python
void_shadow_totals.delay(point_id=123, output_field="total", window_minutes=70)
```

Solo se ejecuta si `VOID_AUTOMATION_ENABLED=True`.

---

## 5. Tests

```bash
python manage.py test void.tests.test_shadow_totals --noinput --keepdb
# Resultado: 4 tests OK

python manage.py test void.tests --noinput --keepdb
# Resultado: 149 tests OK
```

---

## 6. Qué NO incluye este milestone

- Programación automática periódica de shadow (requiere Celery beat).
- Dashboard/reporte visual de diferencias.
- Acción automática ante divergencias (alerta, ticket).
- Shadow mode para nivel/caudal con datos reales de proveedor.

---

## 7. Próximos pasos recomendados (Milestone 9)

1. Programar shadow periódico vía Celery beat para puntos candidatos.
2. Alertar cuando `mismatched_count > 0` en un shadow run.
3. Handler robusto de nivel (`process_nivel_variable`).
4. Caudal promedio/instantáneo legacy.
