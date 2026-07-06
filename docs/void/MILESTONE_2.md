# Milestone 2 — Shadow Mode Automático y Paridad de Procesamiento

> Estado: **cerrado** — shadow mode funciona, paridad verificada en campo, fixes aplicados.  
> Fecha cierre: 2026-07-06  
> Objetivo: tener `void` corriendo automáticamente en paralelo a legacy, comparando totales/flow/nivel cada hora, sin enviar a DGA ni reemplazar legacy todavía.

---

## 1. Contexto

El **Milestone 1** quedó cerrado con los 11 puntos piloto configurados.

**Milestone 2** demostró paridad sostenida de los cálculos clave:

- `total` (totalizador acumulado)
- `flow` (caudal instantáneo/promedio)
- `nivel` (nivel freático)
- `water_table` (d3 - nivel)

---

## 2. Resultado resumido

| Entregable | Estado |
|---|---|
| `ShadowService` compara campos procesados (`output_field`) | ✅ Implementado |
| Comando `void_shadow_report` | ✅ Implementado |
| Shadow mode masivo por total/flow/nivel | ✅ Ejecutado |
| Deduplicación en `IngestService` | ✅ Implementado |
| Orden estable en `PipelineService.process_device_variable` | ✅ Implementado (`timestamp`, `id`) |
| Fórmulas de nivel/caudal ajustadas en `void_sync_legacy` | ✅ Implementado |
| Tests `void.tests` | ✅ 87/87 OK |
| Tests `tests.regression + tests.dga` | ✅ 294/294 OK |
| Envío real a DGA | ⛔ No autorizado (sigue en `auto_send=False`) |
| Reemplazo de cronjobs legacy | ⛔ Fuera de scope |

---

## 3. Fixes aplicados

### 3.1 Deduplicación de ingesta (`void/services/ingest.py`)

`IngestService.ingest_device_variable` ahora omite lecturas cuyo par
`device + variable + timestamp` ya existe en `RawReading`. Esto evita que
re-ingestas masivas dupliquen el offset de totalizadores stateful.

### 3.2 Orden estable de procesamiento (`void/services/pipeline.py`)

`PipelineService.process_device_variable` ordena por `timestamp, id` para
garantizar que lecturas con el mismo timestamp se procesen de forma
determinista y no generen falsos resets parciales.

### 3.3 Fórmulas legacy más fieles (`void/management/commands/void_sync_legacy.py`)

- **NIVEL**: migrado a schema stateful ``Nivel stateful v1``. Replica
  ``process_nivel_variable`` de legacy: raw negativo se reemplaza por el
  nivel histórico más alto, luego se aplica offset y divisor
  ``calculate_nivel``.
- **CAUDAL**: replica `instantaneous_flow` aplicando divisor `calculate_nivel`
  y conversión `/ 3.6` cuando `convert_to_lt=True`.
- **CAUDAL_PROMEDIO**: ya no se sincroniza como variable separada. Se activa
  ``compute_flow=True`` en el totalizador stateful, que calcula el caudal
  promedio como derivada del total: ``(total - total_prev) / Δt * 1000``.

### 3.4 Replicación de último dato (`void/services/replication.py`)

Nuevo campo ``Point.replicate_on_missing`` + ``max_replication_hours``. Cuando
un punto no recibe lecturas, ``ReplicationService`` genera ``ProcessedReading``
sintéticos a partir del último dato válido (comportamiento Nettra legacy).
Tarea Celery: ``void_replicate_missing``.

### 3.5 Feature flag de producción (`api/settings.py`)

Nueva variable ``VOID_AUTOMATION_ENABLED`` (default ``False``). Todas las
tareas Celery de void que ejecutan trabajo real (ingesta, procesamiento,
replicación, envío DGA, shadow sample) se saltan silenciosamente mientras el
flag esté desactivado. Los endpoints y comandos manuales siguen disponibles
para pruebas. Garantiza que void no opere en producción accidentalmente.

---

## 4. Hallazgos de shadow mode

Ver detalles completos en `docs/void/iansa_productos_pilot.md`.

Resumen:

- **Productos Fernández**: paridad alta en total/flow; nivel con diferencias
  por timestamp y corrección de negativos ahora replicada vía schema stateful.
- **Iansa Chillán/Quepe**: totales correctos tras sincronización de offsets;
  flow/nivel requieren validación de fórmulas por diferencias de minuto.
- **Planta 2 P1**: TDATA sin datos recientes; legacy replica último valor
  (`replicate_on_missing`). Ahora void tiene el mismo comportamiento nativo.

### Gaps resueltos en esta fase

1. **Nivel negativo con corrección histórica**: resuelto con schema stateful
   ``Nivel stateful v1``.
2. **CAUDAL_PROMEDIO real**: resuelto con ``compute_flow=True`` en el
   totalizador stateful.
3. **`replicate_on_missing`**: resuelto con campo nativo en ``Point`` y
   ``ReplicationService``.

---

## 5. Qué NO incluye este milestone

- **Envío real a DGA:** requiere confirmación explícita y prueba puntual.
- **Reemplazo de cronjobs legacy:** continúan corriendo.
- **Migración de clientes/usuarios a `void`:** es milestone 3 (CRM/suscripciones).

---

## 6. Próximos pasos recomendados (Milestone 3)

1. Implementar handler stateful para `CAUDAL_PROMEDIO` (derivada del total).
2. Decidir e implementar `replicate_on_missing` configurable por punto.
3. Mejorar corrección de nivel negativo usando histórico (stateful).
4. Activar Celery beat para `void_collect_frequency` + `void_shadow_sample`.
5. Hacer envío de prueba DGA sandbox con `auto_send=True` previa autorización.

---

## 7. Comandos útiles

```bash
# Sincronizar fórmulas actualizadas de un proyecto legacy
python manage.py void_sync_legacy --project-legacy-id 15

# Shadow mode por campo procesado
python manage.py void_shadow_run --device-id <id> --variable input1Count --output-field total

# Reporte de shadow
python manage.py void_shadow_report --hours 24

# Tests
python manage.py test void.tests --noinput --keepdb
python manage.py test tests.regression tests.dga --noinput --keepdb
```
