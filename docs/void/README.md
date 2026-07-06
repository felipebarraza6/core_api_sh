# void — Nueva arquitectura SmartHydro

> **void** es el prototipo de la próxima generación de la plataforma SmartHydro.  
> No reemplaza legacy de un día para otro: convive con él, aprende de él y, cuando esté listo, lo absorbe sin que los endpoints de producción mueran nunca.

---

## 1. ¿Qué es void?

`void` es una app Django independiente (`/void/`) que modela el negocio de SmartHydro de forma limpia:

- **Puntos de captación** (`Point`)
- **Dispositivos / loggers** (`Device`, `DeviceHardware`)
- **Proveedores de telemetría** (`Provider`, `ProviderEndpoint`, `MqttTopicConfig`)
- **Lecturas crudas y procesadas** (`RawReading`, `ProcessedReading`)
- **Procesamiento configurable** (`ProcessingSchema`, `ProcessingStep`, `ProcessingRule`)
- **Cumplimiento regulatorio** (`ComplianceAuthority`, `PointComplianceProfile`, `ComplianceSubmission`)
- **Alertas** (`AlertRule`, `AlertTrigger`)
- **CRM / Suscripciones** (`Client`, `Contract`, `Subscription`, `Invoice`)

La idea es que todo sea **declarativo y configurable**: en vez de código mágico para cada tipo de variable, se definen reglas.

---

## 2. Filosofía

| Legacy | void |
|---|---|
| Tipos de variable fijos (`TOTALIZADO`, `NIVEL`, `CAUDAL`, …) | `processing_type` genérico: `stateful`, `formula`, `passthrough`, `none` |
| Handlers hardcodeados (`controllers/total.py`, `nivel.py`) | Plantillas stateful compartidas que cualquiera puede inspeccionar y clonar |
| Migrar todo de golpe | Convivencia + shadow mode: comparar legacy vs void antes de confiar |
| Configuración escondida en campos del modelo | Configuración explícita en `DeviceVariableConfig` + `ProcessingSchema` |

**Regla de oro:** los endpoints de producción nunca mueren. Legacy sigue funcionando mientras void madura.

---

## 3. Procesamiento de telemetría

### Tipos fundamentales

- **`formula`**: transformación directa con una expresión Python (`(value + offset) / scale`).
- **`stateful`**: reglas con memoria persistente en `DeviceVariableState`. Sirve para totalizadores, contadores, niveles con histórico, alarmas flanqueadas, etc.
- **`passthrough`**: guarda el valor crudo tal cual.
- **`none`**: sin clasificar; marca error para revisión humana.

### Plantillas incluidas

| Plantilla | Qué hace | Paridad legacy |
|---|---|---|
| `Totalizador stateful v1` | Monotonicidad, resets, reconexiones, caudal derivado, diff diario | `controllers/total.py` |
| `Nivel stateful v1` | Corrección de negativos con histórico, cálculo de `nivel` y `water_table` | `process_nivel_variable` |

Cualquiera puede clonar una plantilla, modificar sus reglas y asignarla a una variable sin tocar código.

---

## 4. Flujo típico: configurar un punto

```python
from void.models import Device, Point, Provider
from void.services.handlers.stateful_rulesets import apply_totalizer_schema

# 1. Punto
point = Point.objects.create(
    name="P100 - Captación Río Principal",
    code_internal="UNIPAPEL-P100",
    client="Unipapel",
    project="Planta Valdivia",
    frequency_minutes=60,
    constants={"d3": "10"},
)

# 2. Proveedor
tdata = Provider.objects.create(
    name="TDATA - Unipapel",
    protocol="HTTP_REST",
    auth_type="JWT_REDIS",
    base_url="https://api.tdata.smarthydro.cl",
)

# 3. Device
device = Device.objects.create(
    point=point,
    provider=tdata,
    serial_number="UNI-LOGGER-P100",
    external_id="unipapel_p100",
    configuration={"ingest_token": "tok-unipapel-p100"},
)

# 4. Configurar variable como totalizador
apply_totalizer_schema(
    device=device,
    source_variable="pulses",
    internal_variable="pulses",
    output_field="total",
    pulses_factor=1000,
    max_diff_m3_per_hour=500,
    reconnection_threshold_hours=2,
    compute_flow=True,
)
```

A partir de ahí, cada `RawReading` que llegue se procesa con `PipelineService.process_reading()` y genera un `ProcessedReading`.

---

## 5. Shadow mode

void puede comparar sus resultados contra legacy **sin afectar producción**:

```bash
python manage.py void_shadow_run --device-id <id> --output-field total
```

Esto genera un `ShadowRun` que dice cuántos totales coinciden entre `ProcessedReading` y `InteractionDetail`.

---

## 6. Estado actual

### ✅ Funciona hoy

- Modelo completo de puntos, devices, proveedores, lecturas.
- Pipeline de procesamiento con fórmulas y stateful.
- Plantillas de totalizador y nivel con paridad legacy.
- API REST de ingesta (`/api/void/ingest/`).
- Consumer MQTT básico.
- Compliance: modelos, servicio, retry queue, voucher/tracking_id.
- Alertas: motor de reglas + dispatch async.
- Shadow mode para totales.
- CRM / Suscripciones: esqueleto funcional.

### ⚠️ En construcción / gaps

- Proveedores concretos: ThingsIO, Tago, Novus, NETTRA/TWIN (solo TDATA parcial).
- Caudal instantáneo / promedio legacy exacto.
- Cálculo de días sin conexión (`calculate_days_not_connection`).
- Replicación del último registro cuando no hay datos.
- Envío DGA real integrado al pipeline.
- Migración automática completa de alertas legacy.

---

## 7. Cómo correr tests

```bash
# Tests de void
docker exec django_api_secure python manage.py test void.tests --noinput --keepdb

# Tests de legacy (regresión + DGA)
docker exec django_api_secure python manage.py test tests.regression tests.dga --noinput --keepdb
```

Resultados vigentes:

- `void.tests`: **159/159 OK**
- `tests.regression tests.dga`: **294/294 OK**

---

## 8. Convivencia con legacy

`void` vive al lado de `api.core`. Por ahora:

- `void_sync_legacy` crea puntos/devices en void desde `CatchmentPoint`.
- `void_compare_legacy` compara totales sin tocar datos legacy.
- Los cronjobs legacy siguen siendo los que alimentan producción.

Cuando shadow mode dé verde estable, se puede empezar a enviar datos DGA desde void en paralelo, luego desconectar legacy variable por variable.

---

## 9. Principios de diseño

1. **No hay handlers mágicos.** Todo es `stateful` o `formula`.
2. **Las reglas son datos.** Se pueden versionar, clonar y auditar.
3. **La configuración vive en el modelo**, no en código.
4. **Producción primero.** Nada se activa en void sin validación contra legacy.
5. **Cambios mínimos.** Un solo propósito por iteración.

---

*Última actualización: 2026-07-06*
