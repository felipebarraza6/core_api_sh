# Milestone 7 — Totalizador robusto (paridad legacy)

> Estado: **cerrado** — plantilla stateful replicando la lógica crítica de `controllers/total.py`.  
> Fecha cierre: 2026-07-06  
> Objetivo: que `void` procese totalizados con la misma robustez que legacy (monotonicidad, resets, reconexiones, caudal) usando solo el motor de reglas.

---

## 1. Contexto

El **Milestone 6** cerró con la API REST de alertas.  
El **Milestone 7** ataca uno de los gaps críticos detectados: el pipeline de `void` no replicaba la lógica de totalizado de legacy, lo que lo hacía inseguro para reemplazar `controllers/total.py`.

Se crea una plantilla stateful `Totalizador stateful v1` que:

- Mantiene monotonicidad del total.
- Detecta y compensa resets parciales.
- Mantiene el total ante pulsos negativos, cero o caídas de ruido.
- Detecta reconexiones y no bloquea saltos legítimos.
- Registra saltos masivos pero nunca bloquea (lección aprendida en legacy).
- Calcula caudal derivado, diff de período y diff diaria.
- Genera `CounterResetLog` y `DeviceEvent` para auditoría.

No existe `processing_type='totalizer'`; se usa `processing_type='stateful'` con un `ProcessingSchema` compartido.

---

## 2. Entregables

| Entregable | Estado |
|---|---|
| Plantilla stateful `Totalizador stateful v1` | ✅ |
| Registro en `HandlerRegistry` solo como `processing_type='stateful'` | ✅ |
| `apply_totalizer_schema()` para configurar dispositivos | ✅ |
| Auto-configure de ingesta usa totalizer robusto | ✅ |
| Estado persistente en `DeviceVariableState` | ✅ |
| Cálculo de `total_diff`, `total_today_diff`, `flow` | ✅ |
| Tests de paridad | ✅ 11 tests |
| Tests de void completos | ✅ 145/145 OK |
| Documentación actualizada | ✅ |

---

## 3. Modelo de configuración

`DeviceVariableConfig` con `processing_type='stateful'` y `custom_schema` apuntando a la plantilla `Totalizador stateful v1`:

```python
{
    "pulses_factor": 1000,
    "offset": 0,
    "max_diff_m3_per_hour": 500,
    "reconnection_threshold_hours": 2,
    "compute_flow": True,
}
```

Estado guardado en `DeviceVariableState.state`:

```json
{
  "last_pulses": "10000",
  "last_total": "10500.000",
  "last_timestamp": "2026-07-06T12:00:00+00:00",
  "offset": "10000.000",
  "previous_total": "10000.000",
  "daily_baseline_total": "10000.000",
  "daily_baseline_date": "2026-07-06"
}
```

---

## 4. Flujo del handler

1. Parsear pulsos.
2. Pulsos negativos → error, mantener último total.
3. Calcular `raw_m3 = pulsos * factor / 1000`.
4. Calcular `time_diff` y detectar reconexión.
5. Anti-salto masivo: solo warning, nunca bloquea.
6. Lógica de reset:
   - `pulsos=0` con histórico → mantener total.
   - Caída `<1%` → ruido, mantener.
   - Caída `>90%` sin reconexión → rechazar, mantener.
   - `0 < actual < anterior` válido → reset real, compensar offset.
7. Calcular `total`, `total_diff`, `total_today_diff`, `flow`.
8. Actualizar estado atómicamente.

---

## 5. Uso

### Configurar un device con totalizer robusto

```python
from void.services.handlers.stateful_rulesets import apply_totalizer_schema

apply_totalizer_schema(
    device=device,
    source_variable="pulses",
    internal_variable="total",
    pulses_factor=1000,
    max_diff_m3_per_hour=500,
    reconnection_threshold_hours=2,
    compute_flow=True,
)
```

### Ingesta push con auto-configure

```bash
curl -X POST /void/ingest/ \
  -H "X-Device-Token: <token>" \
  -d '{
    "serial_number": "SN-001",
    "source_variable": "pulses",
    "value": "150",
    "auto_configure": true
  }'
```

Ahora aplica `processing_type='stateful'` con la plantilla de totalizador automáticamente.

---

## 6. Tests

```bash
python manage.py test void.tests.test_totalizer_handler --noinput --keepdb
# Resultado: 11 tests OK

python manage.py test void.tests --noinput --keepdb
# Resultado: 145 tests OK
```

Casos cubiertos:

- acumulación simple,
- pulsos negativos,
- reset a cero,
- reset parcial compensado,
- caída de ruido,
- reconexión,
- salto masivo,
- caudal derivado,
- diff diaria,
- integración con `PipelineService`.

---

## 7. Qué NO incluye este milestone

- Replicar `total_hour`/`total_day` exactamente como legacy (usa InteractionDetail).
  En void se calculan desde `ProcessedReading` + estado.
- Migración automática de dispositivos legacy a plantillas stateful.
- Validación shadow mode de totales contra legacy.

---

## 8. Próximos pasos recomendados (Milestone 8)

1. Shadow mode para totales: comparar `ProcessedReading.total` contra `InteractionDetail.total`.
2. Nivel: plantilla stateful robusta replicando `process_nivel_variable`.
3. Caudal promedio/instantáneo legacy.
4. Migrar dispositivos existentes en `void` de `stateful` a `totalizer` si la comparación shadow es estable.
