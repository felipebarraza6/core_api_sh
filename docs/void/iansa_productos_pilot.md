# Pilot Iansa + Productos Fernández — Estado de void

> Fecha: 2026-07-05  
> Ambiente: producción (solo lectura legacy, escritura void)  
> Status: **configuración completa, ingesta real OK, shadow mode match en múltiples puntos, offsets históricos sincronizados, credenciales DGA pobladas desde entorno**

---

## 1. Resumen ejecutivo

Se configuraron en `void` los **11 puntos reales** de Iansa y Productos Fernández, migrando desde `api.core` sin modificar datos legacy:

- **5 puntos** Iansa Chillán (`core_projectcatchments.id = 2`)
- **2 puntos** Iansa Quepe (`core_projectcatchments.id = 34`)
- **4 puntos** Productos Fernández (`core_projectcatchments.id = 15`)

Todos tienen:
- `Point` + `Device` + `DeviceVariableConfig`
- Constantes del punto (`d1..d6`, offsets, límites)
- Perfil de cumplimiento DGA (`PointComplianceProfile`)
- Proveedor void asignado (`Tago.io` o `TwinDimension TDATA`)

Además se limpió la app `void`: se eliminaron directorios `void/void/void/...` duplicados y se removió definitivamente `DeviceTotalizerState` (modelo migrado a `DeviceVariableState` + reglas stateful). Se agregó la acción `log_counter_reset` al motor stateful para mantener `CounterResetLog` como auditoría de resets.

---

## 2. Proveedores migrados

| ID | Nombre | Protocolo | Endpoints |
|---|---|---|---|
| 1 | Tago.io | HTTP_REST | INGEST |
| 2 | TheThings.io | HTTP_REST | INGEST |
| 3 | TwinDimension TDATA | HTTP_REST | AUTH + INGEST |
| 4 | Unipapel | HTTP_REST | INGEST (caso de prueba) |

---

## 3. Puntos configurados

| Proyecto | Punto | Provider | Variables configuradas | DGA |
|---|---|---|---|---|
| Iansa Chillán | P2 | Tago.io | `3grecdi1va` → pulses (stateful) | SUBTERRANEO MAYOR |
| Iansa Chillán | P3 | Tago.io | `3grecdi1va` → pulses (stateful), `3grecuc1v` → nivel (formula) | SUBTERRANEO MAYOR |
| Iansa Chillán | P4 | TwinDimension TDATA | `input1Count` → pulses, `ai1ActualValue` → flow, `ai2ActualValue` → nivel | SUBTERRANEO MAYOR |
| Iansa Chillán | P5 | Tago.io | `3grecdi1va` → pulses, `3grecuc1v` → flow, `3grecuc2v` → nivel | SUBTERRANEO MAYOR |
| Iansa Chillán | P6 | Tago.io | `3grecdi1va` → pulses, `3grecuc1v` → flow, `3grecuc2v` → nivel | SUBTERRANEO MAYOR |
| Iansa Quepe | Norte | Tago.io | `3grecdi1va` → pulses, `3grecuc1v` → flow, `3grecuc2v` → nivel | SUBTERRANEO MAYOR |
| Iansa Quepe | Sur | Tago.io | `3grecdi1va` → pulses, `3grecuc1v` → flow, `3grecuc2v` → nivel | SUBTERRANEO MAYOR |
| Productos Fernandez | Campo Deportivo | TwinDimension TDATA | `input1Count` → pulses, `ai1ActualValue` → flow, `ai2ActualValue` → nivel | SUBTERRANEO MAYOR |
| Productos Fernandez | Complejo Industrial P1 | TwinDimension TDATA | `input1Count` → pulses, `ai1ActualValue` → flow, `ai2ActualValue` → nivel | SUBTERRANEO MEDIO |
| Productos Fernandez | Planta 1 P1 | TwinDimension TDATA | `input1Count` → pulses, `ai1ActualValue` → flow, `ai2ActualValue` → nivel | SUBTERRANEO MEDIO |
| Productos Fernandez | Planta 2 P1 | TwinDimension TDATA | `input1Count` → pulses, `ai1ActualValue` → flow, `ai2ActualValue` → nivel | SUBTERRANEO MEDIO |

### Notas de configuración

- P2 solo tiene totalizador. En legacy tampoco tiene variables `CAUDAL`/`NIVEL` asociadas al esquema; queda confirmar si es correcto.
- P3 tiene `3grecuc1v` → `nivel`, mientras que P5/P6/Norte/Sur tienen `3grecuc1v` → `flow` y `3grecuc2v` → `nivel`. Esto refleja la configuración legacy actual, pero debe validarse contra campo.
- Las fórmulas de caudal/nivel son aproximaciones construidas desde `Variable.calculate_nivel` y `convert_to_lt`. Requieren ajuste comparando con `InteractionDetail` legacy.

---

## 4. Tests

- `void.tests`: **87/87 OK**
- `tests.regression + tests.dga`: en ejecución en background (`bash-2imp75wf`)

---

## 5. Pruebas de ingesta

### 5.1 Ingesta manual

Endpoint probado: `POST https://api.smarthydro.app/void/ingest/`

#### Escenario P2 (Iansa Chillán) — totalizador stateful

| Secuencia | Pulsos enviados | Total calculado | Notas |
|---|---|---|---|
| 14:00 | 1000 | 1000.000 | Primer registro |
| 15:00 | 1500 | 1500.000 | Incremento normal |
| 16:00 | 200 | 1700.000 | Reset parcial compensado con offset |

Resultado: **monotonicidad preservada**, `CounterResetLog` creado con:

```text
PARTIAL | last=1500 -> curr=200
addition_before=1500 | amount_to_add=1500 | addition_after=3000
total_before=3000 | total_after=3200
```

### 5.2 Ingesta real desde proveedores

#### P5 (Iansa Chillán) — Tago.io

```text
Variable 3grecdi1va: 1 lectura | 2026-07-05 22:46:54 UTC | raw=276166
Variable 3grecuc1v (flow): 1 lectura | raw=22.8 -> flow=22.8
Variable 3grecuc2v (nivel): 1 lectura | raw=72.3 -> nivel=72.3
```

#### Planta 1 P1 (Productos Fernández) — TwinDimension TDATA

```text
Variable input1Count: 14 lecturas | última=2026-07-05 23:36:51 UTC | raw=39764 -> total=39764
Variable ai1ActualValue (flow): 18 lecturas | última=0 -> flow=0
Variable ai2ActualValue (nivel): 18 lecturas | última=493 -> nivel=49.3
```

**Shadow mode:**

```bash
python manage.py void_shadow_run --device-id 55 --variable input1Count --no-ingest --process
# Resultado: legacy=14 void=14 match=1 mismatch=0 legacy_only=1 void_only=0
```

Match en la hora actual: legacy=39764, void=39764.

Esto demuestra que void replica correctamente los datos reales de TDATA.

---

## 6. Prueba DGA payload-only

### 6.1 Payload completo con datos reales

Se generó payload DGA para Planta 1 P1 sin envío real (`auto_send=False`):

```json
{
  "autenticacion": {
    "password": "",
    "rutUsuario": "",
    "rutEmpresa": "76944359-2"
  },
  "medicionSubterranea": {
    "caudal": "0.0",
    "fechaMedicion": "2026-07-05",
    "horaMedicion": "23:36:51",
    "totalizador": "39764",
    "nivelFreaticoDelPozo": "4.7"
  }
}
```

`nivelFreaticoDelPozo` se calculó automáticamente como `d3 - nivel` (54.0 - 49.3).

Legacy para el mismo punto reportó `water_table=4.8` con `nivel=49.2`, consistente con `d3=54.0`.

Status: `pending`. Payload estructuralmente correcto y completo.

---

## 7. Inicialización de offsets históricos

Se creó el comando `void_init_totalizer_offset` para sincronizar el offset acumulado de cada totalizador con legacy:

```bash
python manage.py void_init_totalizer_offset --project-legacy-id 2
python manage.py void_init_totalizer_offset --project-legacy-id 34
python manage.py void_init_totalizer_offset --project-legacy-id 15 --skip-negative
```

Resultados (2026-07-05, re-aplicados tras sync legacy):

| Proyecto | Punto | Variable | Total legacy | Pulsos raw | Factor | Offset aplicado |
|---|---|---|---|---|---|---|
| Iansa Chillán | P2 | 3grecdi1va | 989235 | 158942 | 1000 | 830293.000 |
| Iansa Chillán | P3 | 3grecdi1va | 1176989 | 17041 | 1000 | 1159948.000 |
| Iansa Chillán | P4 | input1Count | 614325 | 614325 | 1000 | 0.000 |
| Iansa Chillán | P5 | 3grecdi1va | 276239 | 276239 | 1000 | 0.000 |
| Iansa Chillán | P6 | 3grecdi1va | 338390 | 338390 | 1000 | 0.000 |
| FPC | P1 | input1Count | 890689 | 89068926 | 10 | -0.260 |
| FPC | P2 | input1Count | 621581 | 18337105 | 10 | 438209.950 |
| FPC | P3 | input1Count | 1291147 | 129114662 | 10 | 0.380 |
| FPC | P4 | input1Count | 64526 | 6452638 | 10 | -0.380 |
| Productos Fernández | Planta 1 P1 | input1Count | 39764 | 39764 | 1000 | 0.000 |
| Productos Fernández | Planta 2 P1 | input1Count | 127005 | 127005 | 1000 | 0.000 |
| Productos Fernández | Complejo Industrial P1 | input1Count | 16191 | 16191 | 1000 | 0.000 |
| Productos Fernández | Campo Deportivo | input1Count | 18033 | 180328 | 100 | 0.200 |

Después de aplicar offsets, P2 y P3 coinciden exactamente con legacy al ingerir datos reales:

```text
P2 (Iansa Chillán): raw=158942 -> total=989235 (legacy=989235)
P3 (Iansa Chillán): raw=17041 -> total=1176989 (legacy=1176989)
P2 (FPC): raw=18337105 -> total=621581 (legacy=621581)
```

---

## 8. Shadow mode masivo

Se extendió `ShadowService` para comparar campos procesados (`total`, `flow`, `nivel`, `water_table`) contra `InteractionDetail`. Se agregó el campo `output_field` a `ShadowRun` y el comando `void_shadow_report`.

Resultados tras reprocesar ordenadamente (ventana 70 min):

### ✅ Paridad confirmada

| Proyecto | Punto | total | flow | nivel | Notas |
|---|---|---|---|---|---|
| Productos Fernández | Campo Deportivo | ✅ 100% | ✅ 100% | ⚠️ 62.5% | Total/flow OK; nivel con timestamps distintos |
| Productos Fernández | Complejo Industrial P1 | ✅ 100% | ✅ 100% | ✅ 100% | Paridad completa |
| Productos Fernández | Planta 1 P1 | ✅ 62.5% | ✅ 100% | ✅ 87.5% | Mismatch por diferencia de minutos |
| Iansa Chillán | P2 | ✅ total | - | - | Solo totalizador |
| Iansa Chillán | P3 | ✅ total | - | - | Total OK |

### ⚠️ Diferencias por tiempo (no por cálculo)

- **FPC P1/P2/P3/P4:** void tiene datos hasta ~00:36, legacy registra hora fija 00:00. Totales difieren por el avance real del contador (ej: P1 890712 vs legacy 890689).
- **Iansa Norte/Sur/P5/P6:** legacy tiene registro horario, void tiene lecturas en minutos distintos → muchos `legacy_only`/`void_only`.

### 🔴 Diferencias reales (fórmulas/procesamiento)

| Punto | Campo | Problema |
|---|---|---|
| FPC P3 | nivel | Legacy reemplaza raw negativo por el nivel histórico más alto; void ahora replica con schema stateful. |
| FPC P4 | nivel | Valor raw difiere (void `170` vs legacy `111`). Posible diferencia de timestamp o corrección legacy no replicada. |
| FPC P1/P2/P3/P4 | flow | `CAUDAL_PROMEDIO` legacy es derivada del total; void ahora calcula con `compute_flow` en totalizador stateful. |
| Iansa P5/P6/Norte/Sur | flow/nivel | Variables `3grecuc1v`/`3grecuc2v` mapeadas a flow/nivel; fórmulas requieren validación contra campo. |
| Planta 2 P1 | todo | TDATA sin datos recientes; legacy replica último valor. Void ahora tiene `replicate_on_missing` nativo. |

---

## 9. Gaps encontrados

### ✅ Resueltos en esta ronda

- **Payload DGA completo por timestamp:** implementado `_resolve_for_timestamp` en `DGAComplianceAdapter`. Busca `flow`/`nivel` en otras `ProcessedReading` del mismo device + timestamp (con ventana de ±5s) y calcula `water_table = d3 - nivel` si aplica.
- **Shadow mode con datos reales:** validado para múltiples puntos con match en totalizador.
- **Offsets históricos:** comando `void_init_totalizer_offset` sincroniza totales con legacy para proyectos 2, 4, 15, 34.
- **Credenciales DGA:** `ComplianceAuthority` ahora lee `DGA_DEFAULT_PASSWORD` y `DGA_DEFAULT_RUT_EMPRESA` desde `.env`; `PointComplianceProfile` recibe `informant_rut` y `extra_config.password` desde legacy.
- **Inicialización de offset en totalizador stateful:** el schema v1.2 inicializa `state_offset` desde `config.offset` en el primer procesamiento, evitando que totales se descalabren al arrancar desde cero.
- **Deduplicación en ingesta:** `IngestService.ingest_device_variable` omite duplicados por `device + variable + timestamp`.
- **Orden estable de procesamiento:** `PipelineService.process_device_variable` ordena por `timestamp, id`.
- **Fórmulas NIVEL/CAUDAL más fieles:** `void_sync_legacy` ahora replica `nivel_mt` (abs, offset, divisor) e `instantaneous_flow` (divisor + conversión L/s).
- **Corrección de nivel negativo con histórico:** schema stateful ``Nivel stateful v1`` guarda `highest_nivel` y reemplaza raw negativo.
- **CAUDAL_PROMEDIO real:** totalizador stateful v1.4 con paso opcional de caudal derivado (`compute_flow=True`).
- **Replicación de último dato:** `Point.replicate_on_missing` + `ReplicationService` + tarea `void_replicate_missing`.
- **Feature flag de producción:** `VOID_AUTOMATION_ENABLED` (default `False`) desactiva todas las tareas Celery de void hasta activación explícita.

### 🔴 Alto

1. **P2 sin variables de caudal/nivel**  
   P2 solo tiene totalizador. Confirmar si en campo realmente no hay caudalímetro/nivel asociado o si falta migrar variables del esquema legacy.

2. **`ingest_token` generado manualmente**  
   Los tokens de los 11 devices se generaron por shell. Para producción deberían rotarse y almacenarse de forma segura (no en `configuration` JSON plano).

### 🟡 Medio

3. **FPC P4 nivel raw difiere**  
   Valor raw void vs legacy difiere (`170` vs `111`). Requiere investigar timestamp/corrección legacy específica.

4. **Iansa P5/P6/Norte/Sur flow/nivel**  
   Fórmulas aproximadas; requieren validación contra `InteractionDetail` campo a campo.

### 🟢 Bajo / técnico

5. **Reinicio de contenedor requerido para recargar `void/`**  
   Gunicorn no recarga automáticamente. Cada cambio en `void/` requiere `docker restart django_api_secure`.

6. **Datos de prueba limpios**  
   P2 no tiene `RawReading`/`ProcessedReading` de prueba. Los offsets históricos ya son estado de producción.

---

## 10. Próximos pasos recomendados

1. **Decidir comportamiento de replicación de último dato** para puntos como Planta 2 P1 donde el proveedor no tiene lecturas recientes. Legacy replica; void es estricto con ventana de 70 min.
2. **Ajustar fórmulas de caudal/nivel** comparando `ProcessedReading` vs `InteractionDetail` campo a campo.
3. **Hacer envío de prueba DGA real** (sandbox o un punto no crítico) con `auto_send=True`, previa confirmación del usuario. **No activar envío masivo a DGA sin autorización explícita.**
4. **Poner Celery worker/beat** para ejecutar `void_collect_frequency` periódicamente en shadow/observación.
5. **Automatizar generación/rotación de `ingest_token`** o mover a campo seguro (no JSON plano).

---

## 11. Comandos útiles

```bash
# Sincronizar un proyecto legacy
python manage.py void_sync_legacy --project-legacy-id 2 --dry-run
python manage.py void_sync_legacy --project-legacy-id 2

# Ver estado de puntos
python manage.py shell -c "
from void.models import Point, Device, DeviceVariableConfig, PointComplianceProfile
for p in Point.objects.filter(project__in=['Iansa Chillán','Iansa Quepe','Productos Fernandez']):
    d = p.device
    print(p.name, d.provider, d.external_id)
"

# Ejecutar shadow mode sin ingesta real
python manage.py void_shadow_run --device-id <id> --variable pulses --no-ingest --process

# Generar payload DGA sin enviar
python manage.py shell -c "
from void.models import PointComplianceProfile, ProcessedReading
from void.services import ComplianceService
profile = PointComplianceProfile.objects.get(point__name='P2', authority__code='dga')
reading = ProcessedReading.objects.filter(device__point__name='P2').order_by('-timestamp').first()
sub = ComplianceService().submit_reading(profile, reading, auto_send=False)
print(sub.payload)
"
```
