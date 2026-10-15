# Tres vistas del totalizador (fuente de verdad)

**Fecha:** 2026-10-02  
**Contexto:** auditoría telemetría (informe v2) — ítem 4 / sección 3.5  
**Código:** `api/core/utils/totalizer.py`

## Resumen

El sistema expone **tres números distintos** llamados “total”. No son tres
cálculos independientes que divergen por bug: parten del **mismo valor
almacenado** y aplican transformaciones documentadas según el consumidor.

| Vista | Fórmula | Dónde | Propósito |
|---|---|---|---|
| **stored** | `(pulsos × pulses_factor) / 1000 + addition` | `InteractionDetail.total` | Continuidad monotónica tras resets del contador físico (`addition` acumula el tramo perdido). |
| **display** (API) | `stored + d6` | Serializer `interaction_detail` / `interaction_detail_json` | Presentación al usuario. `d6` = caudalímetro inicial / baseline histórico de negocio. |
| **dga** | `stored − addition` (= `pulsos × factor / 1000`) | Payload a la DGA (`cron_dga._prepare_response_data`) | Norma DGA: totalizador en escala del sensor, **sin** offset de resets. |

Implementación única: `resolve_totalizer_views(stored, addition, d6)`.

Ejemplo (Iansa P4 #2, auditoría): stored=687.970, d6=10.678.672 → API muestra
11.366.642; DGA recibe stored−addition.

## Por qué no se unifican a un solo número

Unificarlos rompería contratos existentes:

1. **DGA** exige el total del caudalímetro (sin `addition`). Si enviáramos
   `stored`, los comprobantes saltarían tras cada reset compensado.
2. **API/frontend** suma `d6` desde hace años; quitarlo cambia todos los
   dashboards e históricos visibles al cliente.
3. **`stored`** debe incluir `addition` para que `total_diff` / caudal promedio
   y la monotonicidad interna sigan funcionando.

Por eso la “fuente de verdad” es el **valor almacenado + la función de
vistas**, no forzar un único número en todos los canales.

## Nivel negativo (ítem 3 de la auditoría)

**Antes:** `process_nivel_variable` reemplazaba un nivel negativo por el
**máximo histórico** del punto → inventaba lecturas (ej. 94 m en #38) y un
freático `d3 − histórico`.

**Ahora:** se marca como inválido (`variable_values._nivel_invalid`), se
guarda `nivel=0.00` / `water_table=0.00` como centinela (columnas NOT NULL) y
**no** se calcula freático a partir de un nivel inventado. Decisión
documentada; migrar a `NULL` queda pendiente de decisión de Felipe /
cumplimiento (requiere migración de esquema).

## Decisiones abiertas (Felipe / cumplimiento)

1. **Registros ya aceptados por la DGA** con total 0 inventado (ola 28-29 Sep,
   264 comprobantes): **no se reescriben** automáticamente. Rectificación
   ante DGA es decisión de cumplimiento.
2. ¿Exponer `total_stored` / `total_display` / `total_dga` de forma estable en
   la API pública, o solo `total` (= display) como hasta ahora?
3. ¿Migrar `nivel` / `water_table` a nullable para dejar de usar 0.00 como
   centinela de inválido?
